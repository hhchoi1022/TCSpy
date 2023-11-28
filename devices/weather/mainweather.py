#%% 
# Other modules
from astropy.io import ascii
from astropy.time import Time
import time
import json
# Alpaca modules
from alpaca.observingconditions import ObservingConditions
# TCSpy modules
from tcspy.utils.logger import mainLogger
from tcspy.utils import Timeout
from tcspy.configuration import mainConfig

# %%
class mainWeather(mainConfig):
    """
    A class for interfacing with an Alpaca weather device.

    Parameters
    ----------
    1. device : `ObservingConditions`
        The Alpaca weather device to interface with.

    Methods
    -------
    1. get_status() -> dict
        Get the current weather status.
    2. connect() -> None
        Connect to the weather device.
    3. disconnect() -> None
        Disconnect from the weather device.
    4. is_safe() -> bool
        Check if the current weather is safe.
    """
    
    def __init__(self,
                 unitnum : int):
        
        super().__init__(unitnum = unitnum)
        self._unitnum = unitnum
        self._log = mainLogger(unitnum = unitnum, logger_name = __name__+str(unitnum)).log()
        self._checktime = float(self.config['WEATHER_CHECKTIME'])
        self.constraints = self._get_constraints()
        self.device = ObservingConditions(f"{self.config['WEATHER_HOSTIP']}:{self.config['WEATHER_PORTNUM']}",self.config['WEATHER_DEVICENUM'])
        self.condition = 'disconnected'
        self.status = self.get_status()
        
    def get_status(self):
        """
        Get the current weather status.

        Returns
        -------
        status : dict
            A dictionary containing the current weather status.
            Keys:
                - 'update_time': Time stamp of the status update in ISO format.
                - 'jd': Julian date of the status update, rounded to six decimal places.
                - 'name': Name of the weather device.
                - 'is_safe': Flag indicating if the weather is safe.
                - 'temperature': Current temperature.
                - 'humidity': Current humidity.
                - 'pressure': Current atmospheric pressure.
                - 'windspeed': Current wind speed.
                - 'skybrightness': Current sky brightness.
                - 'cloudfraction': Current cloud fraction.
                - 'rainrate': Current rain rate.
                - 'fwhm': Current full-width at half-maximum of stars.
        """

        status = dict()
        status['update_time'] = Time.now().isot
        status['jd'] = round(Time.now().jd,6)
        status['is_connected'] = False
        status['name'] = None
        status['is_safe'] = None
        status['temperature'] = None
        status['humidity'] = None
        status['pressure'] = None
        status['windspeed'] = None
        status['skybrightness'] = None
        status['cloudfraction'] = None
        status['rainrate'] = None
        status['fwhm'] = None
        status['constraints'] = self.constraints

        if self.device.Connected:
            self._update()
            try:
                status['update_time'] = Time.now().isot
            except:
                pass
            try:
                status['jd'] = round(Time.now().jd,6)
            except:
                pass
            try:
                status['name'] = self.device.Name
            except:
                pass
            try:
                status['is_safe'] = self.is_safe()
            except:
                pass
            try:
                status['temperature'] = round(self.device.Temperature,1)
            except:
                pass
            try:
                status['dewpoint'] = round(self.device.DewPoint,1)
            except:
                pass
            try:
                status['humidity'] = round(self.device.Humidity,1)
            except:
                pass
            try:
                status['pressure'] = round(self.device.Pressure,1)
            except:
                pass
            try:
                status['windspeed'] = round(self.device.WindSpeed,1)
            except:
                pass
            try:
                status['windgust'] = round(self.device.WindGust,1)
            except:
                pass
            try:
                status['winddirection'] = round(self.device.WindDirection,1)
            except:
                pass
            try:
                status['skybrightness'] = round(self.device.SkyQuality,2)
            except:
                pass
            try:
                status['skytemperature'] = round(self.device.SkyTemperature,1)
            except:
                pass
            try:
                status['cloudfraction'] = round(self.device.CloudCover,2)
            except:
                pass
            try:
                status['rainrate'] = int(self.device.RainRate)
            except:
                pass
            try:
                status['fwhm'] = round(self.device.StarFWHM,2)
            except:
                pass
            try:
                status['is_connected'] = self.device.Connected
                if status['is_connected']:
                    self.condition = 'idle'
            except:
                pass

        return status
    
    @Timeout(5, 'Timeout')
    def connect(self):
        """
        Connect to the weather device.
        """
        
        self._log.info('Connecting to the weather station...')
        try:
            if not self.device.Connected:
                self.device.Connected = True
            while not self.device.Connected:
                time.sleep(self._checktime)
            if  self.device.Connected:
                self.status['is_connected'] = True
                self.condition = 'idle'
                self._log.info('Weather device connected')
        except:
            self._log.warning('Connection failed')
        self.status = self.get_status()
    
    @Timeout(5, 'Timeout')
    def disconnect(self):
        """
        Disconnect from the weather device.
        """
        
        self.device.Connected = False
        self._log.info('Disconnecting the weather device...')
        while self.device.Connected:
            time.sleep(self._checktime)
        if not self.device.Connected:
            self.status['is_connected'] = False
            self.condition = 'disconnected'
            self._log.info('Weather device disconnected')
        self.status = self.get_status()

    def is_safe(self):
        """
        Check if the current weather is safe.

        Returns
        -------
        1. is_safe : bool
            True if the current weather is safe; False otherwise.
        """
        
        self._update()
        safe_humidity    = self.device.Humidity < self.constraints['HUMIDITY'] 
        safe_rainrate    = self.device.RainRate < self.constraints['RAINRATE'] 
        safe_skymag      = self.device.SkyQuality > self.constraints['SKYMAG'] 
        safe_temperature = (self.device.Temperature > self.constraints['TEMPERATURE_LOWER']) & (self.device.Temperature < self.constraints['TEMPERATURE_UPPER'])
        safe_windspeed   = self.device.WindSpeed < self.constraints['WINDSPEED'] 
        is_safe = safe_humidity & safe_rainrate & safe_skymag & safe_temperature & safe_windspeed
        return is_safe
    
    def _get_constraints(self):
        """
        Get the weather constraints from a file.

        Returns
        -------
        1. constraints : dict
            A dictionary containing the weather constraints.
            Keys:
                - 'HUMIDITY': Maximum humidity.
                - 'RAINRATE': Maximum rain rate.
                - 'SKYMAG': Minimum sky brightness.
                - 'TEMPERATURE_LOWER': Minimum temperature.
                - 'TEMPERATURE_UPPER': Maximum temperature.
                - 'WINDSPEED': Maximum wind speed.
        """
        
        constraints = dict()
        constraints['HUMIDITY'] = self.config['WEATHER_HUMIDITY']
        constraints['RAINRATE'] = self.config['WEATHER_RAINRATE']
        constraints['SKYMAG'] = self.config['WEATHER_SKYMAG']
        constraints['TEMPERATURE_LOWER'] = self.config['WEATHER_TEMPERATURE_UPPER']
        constraints['TEMPERATURE_UPPER'] = self.config['WEATHER_TEMPERATURE_LOWER']
        constraints['WINDSPEED'] = self.config['WEATHER_WINDSPEED']
        return constraints
    
    def _update(self):
        """
        Immediately update the weather device status.
        """
        self.device.Refresh()
        


        
            
        
        
        


# %%

if __name__ =='__main__':
    weather = mainWeather(unitnum = 1)
    weather.connect()
    print(weather.is_safe())
    #weather.disconnect()
# %%
