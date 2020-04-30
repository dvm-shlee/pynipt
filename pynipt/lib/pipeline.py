from .bucket import Bucket
from .plugin import PluginLoader
from ..config import config
from ..errors import *
import time

from IPython import get_ipython
if get_ipython() and len(get_ipython().config.keys()):
    from tqdm import tqdm_notebook as progressbar
    from IPython.display import display
    notebook_env = True
else:
    from pprint import pprint as display
    from tqdm import tqdm as progressbar
    notebook_env = False


class Pipeline(object):
    """ Major user interface to processing pipeline.
    PyNIPT main package does not contain any interface commands or pipeline packages in source code.
    All the interface commands and pipeline packages need to be installed by plugin.

    The default example plugin scripts will be downloaded on your configuration folder
    (under .pynipt/plugin in user's home directory)

    Examples:
        Usage example to select pipeline

        Import module and initiate pipeline object
        >>> import pynipt as pn
        >>> pipe = pn.Pipeline('/project/dataset/path')
        The installed pipeline plugin will be listed here

        >>> pipe.howto(0)       # print help for the 0th pipeline package if any
        The help document will be printed here if the verbose option is True in user's config file

        Select 0th pipeline package
        >>> pipe.set_package(0)
        The available pipelines in the package will be listed here if the verbose option is True in user's config file

        Run 0th pipeline in selected package
        >>> pipe.run(0)
        The description of the pipeline will be printed here if the verbose option is True in user's config file

        Check the progression bar of running pipeline
        >>> pipe.check_progression()

    You can either use default pipeline packages we provide or load custom designed pipelines
    """
    def __init__(self, path, **kwargs):
        """Initiate class

        :param path:    dataset path
        :param logger:  generate log file (default=True)
        :type path:     str
        :type logger:   bool
        """
        # public
        self.selected = None

        # private
        self._bucket                = Bucket(path)
        self._msi                   = self._bucket.msi      #
        self._interface_plugins     = None                  # place holder for interface plugin
        self._n_threads             = None                  # place holder to provide into Interface class
        self._pipeline_title        = None                  # place holder for the pipeline title
        self._plugin                = PluginLoader()
        self._pipeobj               = None
        self._stored_id             = None
        self._progressbar           = None                  # place holder for tqdm module

        # config parser
        cfg = config['Preferences']
        self._logger    = kwargs['logging']     if 'logging'    in kwargs.keys() else cfg.getboolean('logging')
        self._n_threads = kwargs['n_threads']   if 'n_threads'  in kwargs.keys() else cfg.getint('number_of_thread')
        self._verbose   = kwargs['verbose']     if 'verbose'    in kwargs.keys() else cfg.getboolean('verbose')

        if self._verbose:
            # Print out project summary
            print(self._bucket.summary)

            # Print out installed (available) pipeline packages
            avails = ["\t{} : {}".format(*item) for item in self.installed_packages.items()]
            output = ["\nList of installed pipeline packages:"] + avails
            print("\n".join(output))

    def detach_package(self):
        """ Detach selected pipeline package
        """
        self.selected   = None
        self._stored_id = None

    @property
    def installed_packages(self):
        return self._plugin.avail_pkgs

    def set_empty_package(self, title):
        """Initiate empty package with given title

        Args:
            title:
        """
        self._bucket.update()
        self.detach_package()
        # self._interface_plugins = \
        # interface_plugins(self._bucket, title, logger=self._logger, n_threads=self._n_threads)
        self._interface_plugins = self._plugin.get_interfaces()(self._bucket, title,
                                                                logger=self._logger,
                                                                n_threads=self._n_threads)
        self._pipeline_title = title
        if self._verbose is True:
            print('temporary pipeline package [{}] is initiated.'.format(title))

    @property
    def select_package(self):
        """for a backward compatibility"""
        return self.set_package

    def set_package(self, package_id, **kwargs):
        """Initiate package

        :param package_id:  Id code for package to initiate
        :param kwargs:      Input parameters for initiating package
        :type package_id:   int
        :type kwargs:       key=value pairs
        """
        self._bucket.update()

        # convert package ID to package name
        if isinstance(package_id, int):
            self._stored_id = package_id
            self._pipeline_title = self.installed_packages[package_id]
        else:
            raise IndexError
        self.reset(**kwargs)

        if self._verbose:
            print('Description about this package:\n')
            print(self.selected.__init__.__doc__)
            print("The pipeline package '{}' is selected.\n"
                  "Please double check if all parameters are "
                  "correctly provided before run this pipline".format(self._pipeline_title))
            avails = ["\t{} : {}".format(*item) for item in self.selected.installed_pipelines.items()]
            output = ["List of available pipelines in selected package:"] + avails
            print("\n".join(output))

    def reset(self, **kwargs):
        if self._pipeline_title is not None:
            self._interface_plugins = self._plugin.get_interfaces()(self._bucket, self._pipeline_title,
                                                                    logger=self._logger,
                                                                    n_threads=self._n_threads)
            self._pipeobj = self._plugin.get_pkgs(self._stored_id)
            command = 'self.selected = self._pipeobj.{}(self._interface_plugins'.format(self._pipeline_title)
            if kwargs:
                command += ', **{})'.format('kwargs')
            else:
                command += ')'
            exec(command)
        else:
            pass

    def check_progression(self):
        if self._interface_plugins is not None:
            param = self._interface_plugins.scheduler_param
            queued_jobs = len(param['queue'])
            finished_jobs = len(param['done'])
            desc = self.installed_packages[self._stored_id] if self._stored_id is not None else self._pipeline_title
            self._progressbar = progressbar(total=queued_jobs + finished_jobs,
                                            desc=desc,
                                            initial=finished_jobs)

            def workon(n_queued, n_finished):
                while n_finished < n_queued + n_finished:
                    delta = n_queued - len(param['queue'])
                    if delta > 0:
                        n_queued -= delta
                        n_finished += delta
                        self._progressbar.update(delta)
                    time.sleep(0.2)
                self._progressbar.close()

            import threading
            thread = threading.Thread(target=workon, args=(queued_jobs, finished_jobs))
            if notebook_env is True:
                display(self._progressbar)
                thread.start()
            else:
                thread.start()

    def set_param(self, **kwargs):
        """Set parameters

        :param kwargs:      Input parameters for current initiated package
        """
        if self.selected:
            for key, value in kwargs.items():
                if hasattr(self.selected, key):
                    setattr(self.selected, key, value)
                else:
                    raise KeyError
        else:
            raise InvalidApproach('You must select Pipeline Package first.')

    def get_param(self):
        if self.selected:
            # default pipeline method: installed_packages, interface
            return dict([(param, getattr(self.selected, param)) for param in dir(self.selected) if param[0] != '_'
                         if 'pipe_' not in param if param not in ['installed_packages', 'interface']])
        else:
            return None

    def howto(self, idx):
        """ Print help document for package

        Args:
            idx(int):       index of available pipeline package
        """
        if isinstance(idx, int):
            idx = self.installed_packages[idx]
        if idx in self.installed_packages.values():
            command = 'print(self._pipeobj.{}.__init__.__doc__)'.format(idx)
            exec(command)

    def run(self, idx, **kwargs):
        """ Execute selected pipeline

        Args:
            idx(int):       index of available pipeline package
            **kwargs:       key:value pairs of parameters for this pipeline
        """
        self.reset()
        self.set_param(**kwargs)
        if self._verbose:
            exec('print(self.selected.pipe_{}.__doc__)'.format(self.selected.installed_pipelines[idx]))
        exec('self.selected.pipe_{}()'.format(self.selected.installed_pipelines[idx]))

    @property
    def bucket(self):
        return self._bucket

    def remove(self, step_code, mode='processing'):
        if isinstance(step_code, list):
            for s in step_code:
                self.interface.destroy_step(s, mode=mode)
        elif isinstance(step_code, str) and (len(step_code) == 3):
            self.interface.destroy_step(step_code, mode=mode)
        else:
            raise InvalidStepCode

    @property
    def interface(self):
        return self._interface_plugins

    @property
    def schedulers(self):
        running_obj = self._interface_plugins.running_obj
        steps = running_obj.keys()
        return {s : running_obj[s].threads for s in steps}

    @property
    def managers(self):
        running_obj = self._interface_plugins.running_obj
        steps = running_obj.keys()
        return {s: running_obj[s].mngs for s in steps}

    def get_builder(self):
        if self.interface is not None:
            from .interface import InterfaceBuilder
            return InterfaceBuilder(self.interface)
        else:
            return None

    def get_dset(self, step_code, ext='nii.gz', regex=None):
        if self.interface is not None:
            proc = self.interface
            proc.update()
            filter_ = dict(pipelines=proc.label,
                           ext=ext)
            if regex is not None:
                filter_['regex'] = regex
            try:
                step = proc.get_step_dir(step_code)
            except KeyError:
                try:
                    step = proc.get_report_dir(step_code)
                except KeyError:
                    step = proc.get_mask_dir(step_code)

            if step_code in proc.executed.keys():
                dataclass = 1
                filter_['steps'] = step
            elif step_code in proc.reported.keys():
                dataclass = 2
                filter_['reports'] = step
            elif step_code in proc.masked.keys():
                dataclass = 3
                filter_['datatypes'] = step
                del filter_['pipelines']
            else:
                return None
            return self.bucket(dataclass, copy=True, **filter_)
        else:
            return None

    def __repr__(self):
        return self.summary

    @property
    def summary(self):
        return str(self._summary())

    def _summary(self):
        if self._pipeline_title is not None:
            self.interface.update()
            s = ['** List of existing steps in selected package [{}]:\n'.format(self._pipeline_title)]
            if len(self.interface.executed) is 0:
                pass
            else:
                s.append("- Processed steps:")
                for i, step in sorted(self.interface.executed.items()):
                    s.append("\t{}: {}".format(i, step))
            if len(self.interface.reported) is 0:
                pass
            else:
                s.append("- Reported steps:")
                for i, step in sorted(self.interface.reported.items()):
                    s.append("\t{}: {}".format(i, step))
            if len(self.interface.masked) is 0:
                pass
            else:
                s.append("- Mask data:")
                for i, step in sorted(self.interface.masked.items()):
                    s.append("\t{}: {}".format(i, step))
            if len(self.interface.waiting_list) is 0:
                pass
            else:
                s.append("- Queue:")
                s.append("\t{}".format(', '.join(self.interface.waiting_list)))
            output = '\n'.join(s)
            return output
        else:
            return None


class PipelineBuilder(object):
    """ The class for building a pipeline plugin

    """
    def __init__(self, interface):
        self._interface = interface

    @property
    def interface(self):
        return self._interface

    @property
    def installed_pipelines(self):
        pipes = [pipe[5:] for pipe in dir(self) if 'pipe_' in pipe]
        output = dict(zip(range(len(pipes)), pipes))
        return output
