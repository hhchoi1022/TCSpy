#%%
# Other modules
from astropy.coordinates import SkyCoord
import time
from astropy.time import Time
import astropy.units as u
from threading import Event

from tcspy.devices import PWI4 # PWI4 API 
from tcspy.configuration import mainConfig
from tcspy.devices.observer import mainObserver
from tcspy.utils.logger import mainLogger
from tcspy.utils import to_SkyCoord
from tcspy.utils import Timeout
from tcspy.utils.exception import *
#%%

class mainMount_pwi4(mainConfig):
    """
    A class representing a telescope that uses the PWI4 protocol.

    Parameters
    ----------
    unitnum : int
        The unit number of the telescope.

    Attributes
    ----------
    observer : mainObserver
        An instance of the mainObserver class used for observation.
    device : PWI4
        An instance of the PWI4 class representing the telescope device.
    status : dict
        The current status of the telescope.

    Methods
    -------
    get_status() -> dict
        Get the current status of the telescope.
    connect() -> bool
        Connect to the telescope.
    disconnect() -> bool
        Disconnect from the telescope.
    set_park(altitude: float = 40, azimuth: float = 180) -> None
        Set the park position of the telescope.
    park(abort_action: Event, disable_mount=False) -> bool
        Park the telescope.
    unpark() -> bool
        Unpark the telescope.
    find_home(abort_action: Event) -> bool
        Find the home position of the telescope.
    slew_radec(ra: float, dec: float, abort_action: Event, tracking=True) -> bool
        Slew the telescope to a specified RA/Dec coordinate.
    slew_altaz(alt: float, az: float, abort_action: Event, tracking=False) -> bool
        Slews the telescope to the specified Alt-Azimuth coordinate.
    tracking_on() -> bool
        Activates the tracking mode of the mount.
    tracking_off() -> bool
        Deactivates the tracking mode of the mount.
    abort() -> None
        Abort the movement of the mount.
    """

    def __init__(self,
                 unitnum : int,
                 **kwargs):
        
        super().__init__(unitnum = unitnum)
        self._unitnum = unitnum
        self._log = mainLogger(unitnum = unitnum, logger_name = __name__+str(unitnum)).log()
        self._min_altitude = float(self.config['TARGET_MINALT'])
        self._max_altitude = float(self.config['TARGET_MAXALT'])
        self._checktime = float(self.config['MOUNT_CHECKTIME'])
        self._settle_time = float(self.config['MOUNT_SETTLETIME'])
        self.observer = mainObserver()
        self.device = PWI4(self.config['MOUNT_HOSTIP'], self.config['MOUNT_PORTNUM'])
        self.status = self.get_status()
    
    def get_status(self):
        """
        Get the current status of the telescope.

        Returns
        -------
        status : dict
            A dictionary containing various status information.
        """
        status = dict()
        status['update_time'] = Time.now().isot
        status['jd'] = "{:.6f}".format(Time.now().jd)
        status['ra'] = None
        status['dec'] = None
        status['ra_hour'] = None
        status['dec_deg'] = None
        status['alt'] = None
        status['az'] = None
        status['at_parked'] = None
        status['at_home'] = None
        status['is_connected'] = None
        status['is_tracking'] = None
        status['is_slewing'] = None
        status['is_stationary'] = None
        status['axis1_rms'] = None
        status['axis2_rms'] = None
        status['axis1_maxvel'] = None
        status['axis2_maxvel'] = None
        try:
            if self.PWI_status.mount.is_connected:
                PWI_status = self.PWI_status
                status['update_time'] = PWI_status.response.timestamp_utc
                status['jd'] = "{:.6f}".format(PWI_status.mount.julian_date)
                coordinates = SkyCoord(PWI_status.mount.ra_j2000_hours, PWI_status.mount.dec_j2000_degs, unit = (u.hourangle, u.deg) )
                status['ra'] =  float("{:.4f}".format(coordinates.ra.deg))
                status['dec'] =  float("{:.4f}".format(coordinates.dec.deg))
                status['ra_hour'] = "{:.4f}".format(PWI_status.mount.ra_j2000_hours)
                status['dec_dec'] = "{:.4f}".format(PWI_status.mount.dec_j2000_degs)
                status['alt'] = "{:.3f}".format(PWI_status.mount.altitude_degs)
                status['az'] = "{:.3f}".format(PWI_status.mount.azimuth_degs)
                status['at_parked'] = (PWI_status.mount.axis0.is_enabled == False) & (PWI_status.mount.axis1.is_enabled == False)
                status['is_connected'] = PWI_status.mount.is_connected
                status['is_tracking'] = PWI_status.mount.is_tracking
                status['is_slewing'] = PWI_status.mount.is_slewing 
                status['is_stationary'] = (PWI_status.mount.axis0.rms_error_arcsec < self.config['MOUNT_RMSRA']) & (PWI_status.mount.axis1.rms_error_arcsec < self.config['MOUNT_RMSDEC']) & (not PWI_status.mount.is_slewing)
                status['axis1_rms'] = "{:.4f}".format(PWI_status.mount.axis0.rms_error_arcsec)
                status['axis2_rms'] = "{:.4f}".format(PWI_status.mount.axis1.rms_error_arcsec)
                status['axis1_maxvel'] = "{:.4f}".format(PWI_status.mount.axis0.max_velocity_degs_per_sec)
                status['axis2_maxvel'] = "{:.4f}".format(PWI_status.mount.axis1.max_velocity_degs_per_sec)
        except:
            pass
        return status
    
    @property
    def PWI_status(self):
        """
        Get the PWI status of the telescope.
        """
        return self.device.status()
    
    @Timeout(5, 'Timeout')
    def connect(self):
        """
        Connect to the telescope.
        """
        self._log.info('Connecting to the telescope...')
        status = self.get_status()
        try:
            if not status['is_connected']:
                self.device.mount_connect()
            time.sleep(self._checktime)
            while not status['is_connected']:
                time.sleep(self._checktime)
                status = self.get_status()
            if status['is_connected']:
                self._log.info('Mount connected')
                
        except:
            self._log.critical('Connection failed')
            raise ConnectionException('Connection failed')
        return True
    
    @Timeout(5, 'Timeout')
    def disconnect(self):
        """
        Disconnect from the telescope.
        """
        self._log.info('Disconnecting to the telescope...')
        status = self.get_status()
        try:
            if status['is_connected']:
                self.device.mount_disconnect()
            time.sleep(self._checktime)
            while status['is_connected']:
                time.sleep(self._checktime)
                status = self.get_status() 
            if not status['is_connected']:
                self._log.info('Mount disconnected')

        except:
            self._log.critical('Disconnect failed')
            raise ConnectionException('Disconnect failed')
        return True
    
    def enable(self):
        """
        Enable the mount axes.
        """
        for axis_index in range(2):
            PWI_status = self.PWI_status
            try:
                if not PWI_status.mount.axis[axis_index].is_enabled:
                    self.device.mount_enable(axisNum= axis_index)
                else:
                    pass
            except:
                self._log.critical('Mount cannot be enabled')
                raise MountEnableFailedException()
            self._log.info('Both axis are enabled ')
        return True
    
    def disable(self):
        """
        Disable the mount axes.
        """
        for axis_index in range(2):
            PWI_status = self.PWI_status
            try:
                if PWI_status.mount.axis[axis_index].is_enabled:
                    self.device.mount_disable(axisNum= axis_index)
                else:
                    pass
            except:
                self._log.critical('Mount cannot be disabled')
                raise MountEnableFailedException()
            self._log.info('Both axis are disabled ')
        return True
    
    def park(self, abort_action : Event, disable_mount = False):
        """
        Park the telescope.

        Parameters
        ----------
        abort_action : Event
            An Event object to signal the abort action.
        disable_mount : bool, optional
            Whether to disable the mount after parking.
        """
        coordinate = SkyCoord(self.config['MOUNT_PARKAZ'],self.config['MOUNT_PARKALT'], frame = 'altaz', unit ='deg')
        alt = coordinate.alt.deg
        az = coordinate.az.deg

        self._log.info('Parking telescope...')
        status = self.get_status()
        # Check the mount is enabled to slew
        if status['at_parked']:
            try:
                self.enable()
            except MountEnableFailedException:
                raise ParkingFailedException('Mount parking is failed : Mount enable failed')
        
        # Slew
        try:
            self.device.mount_goto_alt_az(alt_degs = alt, az_degs = az)
        except:
            self._log.critical('Mount parking is failed')
            raise ParkingFailedException('Mount parking is failed : Slewing failed')
        time.sleep(self._checktime)
        status = self.get_status()
        while status['is_slewing']:
            time.sleep(self._checktime)
            status = self.get_status()
            if abort_action.is_set():
                self.abort()
                self._log.warning('Mount parking is aborted')
                raise AbortionException('Mount parking is aborted')
        time.sleep(self._checktime)
        
        # Disable mount when disable == True
        if disable_mount:
            try:
                self.disable()
            except MountEnableFailedException:
                self._log.critical('Parking failed')
                raise ParkingFailedException('Mount parking is failed : Mount disable failed')
        self._log.info('Mount parked')
        return True

    def unpark(self):
        """
        Unpark the telescope.
        """
        self._log.info('Unparking telescope...')
        try:
            self.enable()
            self._log.info('Mount unparked')
        except MountEnableFailedException:
            self._log.critical('Unparking failed')
            raise ParkingFailedException('Unparking failed')
        return True
    
    def find_home(self, abort_action : Event):
        """
        Find the home position of the telescope.

        Parameters
        ----------
        abort_action : Event
            An Event object to signal the abort action.
        """
        self._log.info('Finding home position...')
        # Check whether mount is parked 
        status = self.get_status()
        if status['at_parked']:
            try:
                self.unpark()
            except ParkingFailedException:
                raise FindingHomeFailedException('Mount homing failed : Unparking failed')
        
        # Find home
        self.device.mount_find_home()            
        
        time.sleep(self._checktime)
        status = self.get_status()
        while not status['is_stationary']:
            time.sleep(self._checktime)
            status = self.get_status()
            if abort_action.is_set():
                self.abort()
                self._log.warning('Mount homing is aborted')
                raise AbortionException('Mount homing is aborted')
        self._log.info('Mount homed')
        return True

    def slew_radec(self,
                   ra : float,
                   dec : float,
                   abort_action : Event,
                   force_action : bool = False,
                   tracking = True):
        """
        Slew the telescope to a specified RA/Dec coordinate.

        Parameters
        ----------
        ra : float
            The Right Ascension of the target in decimal hours.
        dec : float
            The Declination of the target in decimal degrees.
        abort_action : Event
            An Event object to signal the abort action.
        tracking : bool, optional
            Whether to turn tracking on after slewing.
        """
        from tcspy.utils.target.singletarget import SingleTarget

        target = SingleTarget(observer = self.observer, ra = float(ra), dec = float(dec))
        altaz = target.altaz()
        self._log.info('Slewing to the coordinate (RA = %.3f, Dec = %.3f, Alt = %.1f, Az = %.1f)' %(ra, dec, altaz.alt.deg, altaz.az.deg))

        # Check coordinates
        if force_action:
            self._log.warning('Forced slewing: Destination altitude below limit (%.1fdeg)' %altaz.alt.deg)
        else:
            if altaz.alt.deg < self._min_altitude:
                self._log.critical('Destination altitude below limit (%.1fdeg)' %altaz.alt.deg)
                raise SlewingFailedException('Destination altitude below limit (%.1fdeg)' %altaz.alt.deg)
        
        # Check whether the mount is parked
        status = self.get_status()
        if status['at_parked']:
            try:
                result_unpark = self.unpark()
            except ParkingFailedException:
                raise SlewingFailedException('Mount slewing is failed : Unparking failed')
        
        # Slew
        self.device.mount_goto_ra_dec_j2000(target.ra_hour, target.dec_deg)
        time.sleep(self._checktime)
        status = self.get_status()
        while status['is_slewing']:
            time.sleep(self._checktime)
            status = self.get_status()
            if abort_action.is_set():
                self.abort()
                self._log.warning('Mount parking is aborted')
                raise AbortionException('Mount slewing is aborted')
        self._log.info(f'Mount settling for {self.config["MOUNT_SETTLETIME"]}s...' )
        time.sleep(self._settle_time)
        status = self.get_status()
        self._log.info('Slewing finished. Current coordinate (RA = %.3f, Dec = %.3f, Alt = %.1f, Az = %.1f)' %(float(status['ra']), float(status['dec']), float(status['alt']), float(status['az'])))
        if not tracking:
            try:
                self.tracking_off()
            except TrackingFailedException:
                raise SlewingFailedException('Mount slewing is failed : Tracking failed')
        else:
            try:
                self.tracking_on()
            except TrackingFailedException:
                raise SlewingFailedException('Mount slewing is failed : Tracking failed')                    
        return True
    
    def slew_altaz(self,
                   alt : float,
                   az : float,
                   abort_action : Event,
                   force_action : bool = False,
                   tracking = False):
        """
        Slews the telescope to the specified Alt-Azimuth coordinate.

        Parameters
        ----------
        alt : float
            The target altitude in degrees.
        az : float
            The target azimuth in degrees.
        abort_action : Event
            An Event object to signal the abort action.
        tracking : bool, optional
            If True, tracking will be enabled after slewing.
        """
        self._log.info('Slewing to the coordinate (Alt = %.1f, Az = %.1f)' %(alt, az))

        # Check coordinates
        if force_action:
            self._log.warning('Forced slewing: Destination altitude below limit (%.1fdeg)' %alt)
        else:
            if alt < self._min_altitude:
                self._log.critical('Destination altitude below limit (%.1fdeg)' %alt)
                raise SlewingFailedException('Destination altitude below limit (%.1fdeg)' %alt)
        
        # Check whether the mount is parked

        status = self.get_status()
        if status['at_parked']:
            try:
                result_unpark = self.unpark()
            except ParkingFailedException:
                raise SlewingFailedException('Mount slewing is failed : Unparking failed')
          
        # Slew
        self.device.mount_goto_alt_az(alt_degs = alt, az_degs = az)
        time.sleep(self._checktime)
        status = self.get_status()
        while status['is_slewing']:
            time.sleep(self._checktime)
            status = self.get_status()
            if abort_action.is_set():
                self.abort()
                self._log.warning('Mount parking is aborted')
                raise AbortionException('Mount slewing is aborted')
        self._log.info(f'Mount settling for {self.config["MOUNT_SETTLETIME"]}s...' )
        time.sleep(self._settle_time)    
        status = self.get_status()
        self._log.info('Slewing finished. Current coordinate (Alt = %.1f, Az = %.1f)' %(float(status['alt']), float(status['az'])))
        if not tracking:
            try:
                self.tracking_off()
            except TrackingFailedException:
                raise SlewingFailedException('Mount slewing is failed : Tracking failed')
        else:
            try:
                self.tracking_on()
            except TrackingFailedException:
                raise SlewingFailedException('Mount slewing is failed : Tracking failed')                    
        return True

    def tracking_on(self):
        """
        Activates the tracking mode of the mount.
        """
        status = self.get_status()
        if not status['is_tracking']:
            try:
                self.device.mount_tracking_on()
            except:
                self._log.critical('Tracking failed')
                raise TrackingFailedException('Tracking failed')
        else:
            pass
        self._log.info('Tracking activated')
        return True
        
    def tracking_off(self):
        """
        Deactivates the tracking mode of the mount.
        """
        status = self.get_status()
        if status['is_tracking']:
            try:
                self.device.mount_tracking_off()
            except:
                self._log.critical('Untracking failed')
                raise TrackingFailedException('Untracking failed')
        else:
            self._log.info('Tracking deactivated')
        return True        
    
    def abort(self):
        """
        Abort the movement of the mount
        """        
        self.device.mount_stop()

# %%
if __name__ == '__main__':
    tel  =mainMount_pwi4(unitnum = 1)
    tel.slew_altaz(alt = 35, az = 270, abort_action = Event())
    
#%%