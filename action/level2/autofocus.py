#%%
#%%
import os
import json
from astropy.time import Time
from multiprocessing import Event
from multiprocessing import Manager

from tcspy.devices import SingleTelescope
from tcspy.devices import TelescopeStatus
from tcspy.interfaces import *
from tcspy.utils.error import *
from tcspy.utils.exception import *
from tcspy.utils.logger import mainLogger

from tcspy.action.level1 import ChangeFocus
from tcspy.action.level1 import ChangeFilter

#%%

class AutoFocus(Interface_Runnable, Interface_Abortable):
    """
    A class representing the autofocus action for a single telescope.

    Parameters
    ----------
    singletelescope : SingleTelescope
        An instance of SingleTelescope class representing an individual telescope to perform the autofocus action on.
    abort_action : Event
        An instance of the built-in Event class to handle the abort action. 

    Attributes
    ----------
    telescope : SingleTelescope
        The SingleTelescope instance on which the autofocus action has to be performed.
    telescope_status : TelescopeStatus
        A TelescopeStatus instance which is used to check the current status of the telescope.
    abort_action : Event
        An instance of Event to handle the abort action.

    Methods
    -------
    run(filter_: str, use_offset: bool)
        Performs the action of starting autofocus for the telescope.
    abort()
        Stops any autofocus action currently being carried out by the telescope.
    """
    
    def __init__(self, 
                 singletelescope : SingleTelescope,
                 abort_action : Event):
        self.telescope = singletelescope
        self.telescope_status = TelescopeStatus(self.telescope)
        self.abort_action = abort_action
        self.shared_memory_manager = Manager()
        self.shared_memory = self.shared_memory_manager.dict()
        self._log = mainLogger(unitnum = self.telescope.unitnum, logger_name = __name__+str(self.telescope.unitnum)).log()
    
    def run(self,
            filter_ : str,
            use_offset : bool):
        """
        Performs the action of starting autofocus for the telescope.

        Parameters
        ----------
        filter_ : str
            The name of the filter to use during autofocus.
        use_offset : bool
            Whether or not to use offset during autofocus.

        Raises
        ------
        ConnectionException:
            If the required devices are disconnected.
        AbortionException:
            If the action is aborted during execution.
        ActionFailedException:
            If the autofocus process fails.
        """
        self._log.info(f'[{type(self).__name__}] is triggered.')
        # Check device status
        status_camera = self.telescope_status.camera
        status_focuser = self.telescope_status.focuser
        status_mount = self.telescope_status.mount
        status_filterwheel = self.telescope_status.filterwheel
        trigger_abort_disconnected = False
        if status_camera.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Camera is disconnected. Action "{type(self).__name__}" is not triggered')
        if status_focuser.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Focuser is disconnected. Action "{type(self).__name__}" is not triggered')
        if status_mount.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Mount is disconnected. Action "{type(self).__name__}" is not triggered')
        if status_filterwheel.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Filterwheel is disconnected. Action "{type(self).__name__}" is not triggered')
        if trigger_abort_disconnected:
            raise ConnectionException(f'[{type(self).__name__}] is failed: devices are disconnected.')
        
        # Abort action when triggered
        if self.abort_action.is_set():
            self.abort()
            self._log.warning(f'[{type(self).__name__}] is aborted.')
            raise  AbortionException(f'[{type(self).__name__}] is aborted.')
        
        if use_offset:
            info_filterwheel = self.telescope.filterwheel.get_status()
            current_filter = info_filterwheel['filter']
            if not current_filter == filter_:
                offset = self.telescope.filterwheel.get_offset_from_currentfilt(filter_ = filter_)
                self._log.info(f'Focuser is moving with the offset of {offset}[{current_filter} >>> {filter_}]')
                try:
                    action_changefocus = ChangeFocus(singletelescope = self.telescope, abort_action = self.abort_action)
                    result_focus = action_changefocus.run(position = offset, is_relative= True)
                except ConnectionException:
                    self._log.critical(f'[{type(self).__name__}] is failed: Focuser is disconnected.')                
                    raise ConnectionException(f'[{type(self).__name__}] is failed: Focuser is disconnected.')                
                except AbortionException:
                    self._log.warning(f'[{type(self).__name__}] is aborted.')
                    raise AbortionException(f'[{type(self).__name__}] is aborted.')
                except ActionFailedException:
                    self._log.critical(f'[{type(self).__name__}] is failed: Focuser movement failure.')
                    raise ActionFailedException(f'[{type(self).__name__}] is failed: Focuser movement failure.')
            
        # Change filter
        info_filterwheel = self.telescope.filterwheel.get_status()
        current_filter = info_filterwheel['filter']
        if not current_filter == filter_:
            try:
                result_filterchange = ChangeFilter(singletelescope = self.telescope, abort_action = self.abort_action).run(filter_ = filter_)
            except ConnectionException:
                self._log.critical(f'[{type(self).__name__}] is failed: Filterwheel is disconnected.')                
                raise ConnectionException(f'[{type(self).__name__}] is failed: Filterwheel is disconnected.')                
            except AbortionException:
                self._log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
            except ActionFailedException:
                self._log.critical(f'[{type(self).__name__}] is failed: Filterwheel movement failure.')
                raise ActionFailedException(f'[{type(self).__name__}] is failed: Filterwheel movement failure.')
        
        # run Autofocus
        info_focuser = self.telescope.focuser.get_status()
        self._log.info(f'Start autofocus [Central focus position: {info_focuser["position"]}, filter: {filter_}]')
        try:
            result_autofocus, autofocus_position = self.telescope.focuser.autofocus_start(abort_action = self.abort_action)
        except AbortionException:
            self._log.warning(f'[{type(self).__name__}] is aborted.')
            raise AbortionException(f'[{type(self).__name__}] is aborted.')
        except AutofocusFailedException:
            self._log.warning(f'[{type(self).__name__}] is failed: Autofocus process is failed. Focuser move back to the previous position')
            action_changefocus.run(position = info_focuser['position'], is_relative= False)
            raise ActionFailedException(f'[{type(self).__name__}] is failed: Autofocus process is failed')
        
        if result_autofocus:
            self._log.info(f'[{type(self).__name__}] is finished')
            self.shared_memory['succeeded'] = result_autofocus
            self.update_focus_history(filter_ = filter_, focusval =autofocus_position, is_succeeded = result_autofocus)
            return True
    
    def update_focus_history(self, filter_ : str, focusval : float, is_succeeded : bool, focus_history_file = './focus_history.data'):
        def write_default_focus_history(filtinfo_file = '../../configuration/filtinfo.data',
                                        output_file = './focus_history.data'):
            with open(filtinfo_file, 'r') as f:
                filtinfo = json.load(f)
            default_focus_history_filter = dict(zip(['update_time', 'succeeded', 'focusval'], [Time('2000-01-01').isot, False, 10000]))
            focus_history_default = dict()
            for tel_name, filt_list in filtinfo.items():
                focus_history_telescope = dict()
                for filt_name in filt_list:
                    focus_history_telescope[filt_name] = default_focus_history_filter
                focus_history_default[tel_name] = focus_history_telescope
            with open(output_file, 'w') as f:
                json.dump(focus_history_default, f, indent=4)
        if not os.path.isfile(focus_history_file):
            print('No focus_hostory file exists. Default format is generated.')
            write_default_focus_history(output_file = focus_history_file)
        with open(focus_history_file, 'r') as f:
            focus_history_data = json.load(f)
        focus_history_data[self.telescope.tel_name][filter_]['update_time'] = Time.now().isot
        focus_history_data[self.telescope.tel_name][filter_]['succeeded'] = is_succeeded
        focus_history_data[self.telescope.tel_name][filter_]['focusval'] = focusval
        with open(focus_history_file, 'w') as f:
            json.dump(focus_history_data, f, indent=4)
        
    
    def abort(self):
        """
        Stops any autofocus action currently being carried out by the telescope.

        Raises
        ------
        AbortionException:
            When the autofocus action is aborted.
        """
        info_focuser = self.telescope.focuser.get_status()
        if info_focuser['is_autofousing']:
            self.telescope.focuser.autofocus_stop()
        if info_focuser['is_moving']:
            self.telescope.focuser.abort()
        return 

# %%
A = AutoFocus(SingleTelescope(21), Event())
# %%
A.run('m450', False)
# %%
