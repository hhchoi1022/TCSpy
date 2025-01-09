#%%
from multiprocessing import Event
from multiprocessing import Manager

from tcspy.devices import SingleTelescope
from tcspy.devices import TelescopeStatus
from tcspy.interfaces import *
from tcspy.utils.logger import mainLogger
from tcspy.utils.exception import *

class TrackingOn(Interface_Runnable, Interface_Abortable):
    """
    A class to perform the action of turning on the tracking of a telescope.

    Parameters
    ----------
    singletelescope : SingleTelescope
        A SingleTelescope instance to perform the action on.
    abort_action : Event
        An instance of Event to handle the abort action.

    Attributes
    ----------
    telescope : SingleTelescope
        The SingleTelescope instance on which to perform the action.
    telescope_status : TelescopeStatus
        The TelescopeStatus instance used to check the current status of the telescope.
    abort_action : Event
        An instance of Event to handle the abort action.

    Methods
    -------
    run()
        Turn on the tracking of the telescope.
    abort()
        This method does nothing but should be overridden in the subclasses if needed.
    """
    def __init__(self, 
                 singletelescope : SingleTelescope,
                 abort_action : Event):
        self.telescope = singletelescope
        self.telescope_status = TelescopeStatus(self.telescope)
        self.abort_action = abort_action
        self.shared_memory_manager = Manager()
        self.shared_memory = self.shared_memory_manager.dict()
        self.shared_memory['succeeded'] = False
        self.is_running = False
        
    def run(self):
        """
        Turn on the tracking of the telescope.

        Raises
        ------
        ConnectionException
            If the telescope is disconnected.
        ActionFailedException
            If the action of turning on tracking failed.
        
        Returns
        -------
        bool
            True if the action is finished, False otherwise.
        """
        self.telescope.register_logfile()
        self.telescope.log.info(f'=====LV1[{type(self).__name__}] is triggered.')
        self.is_running = True
        self.shared_memory['succeeded'] = False
        # Check device connection
        mount = self.telescope.mount  
        status_mount = self.telescope_status.mount.lower()

        # Start action
        if status_mount == 'disconnected':
            self.is_running = False
            self.telescope.log.critical(f'=====LV1[{type(self).__name__}] is failed: mount is disconnected.')
            raise ConnectionException(f'[{type(self).__name__}] is failed: mount is disconnected.')
        elif status_mount == 'parked':
            self.is_running = False
            self.telescope.log.critical(f'=====LV1[{type(self).__name__}] is failed: mount is parked.')
            raise ActionFailedException(f'[{type(self).__name__}] is failed: mount is parked.')
        elif status_mount == 'busy':
            self.is_running = False
            self.telescope.log.critical(f'=====LV1[{type(self).__name__}] is failed: mount is busy.')
            raise ActionFailedException(f'[{type(self).__name__}] is failed: mount is busy.')
        else:
            try:
                result_tracking = self.telescope.mount.tracking_on()
            except TrackingFailedException:
                self.is_running = False
                self.telescope.log.critical(f'=====LV1[{type(self).__name__}] is failed: mount siderialtracking failure.')
                raise ActionFailedException(f'[{type(self).__name__}] is failed: mount siderialtracking failure.')        
        if result_tracking:    
            self.shared_memory['succeeded'] = True
        
        self.is_running = False
        self.telescope.log.info(f'=====LV1[{type(self).__name__}] is finished.')                
        if self.shared_memory['succeeded']:
            return True    
        
    def abort(self):
        self.abort_action.set()
        self.is_running = False
        self.telescope.log.warning(f'=====LV1[{type(self).__name__}] is aborted.')
        raise AbortionException(f'[{type(self).__name__}] is aborted.')