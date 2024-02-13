#%%
from tcspy.devices import PWI4

#%%
file_key = '/Users/hhchoi1022/Test_samples/231207/7DT01/*.fits'
files = sorted(glob.glob(file_key))
#%%
file = files[20]
#%%
def crop_image(data, 
               center_x : int,
               center_y : int,
               crop_size : int):
    x_start = max(0, center_x - crop_size // 2)
    x_end = min(data.shape[1], center_x + crop_size // 2)
    y_start = max(0, center_y - crop_size // 2)
    y_end = min(data.shape[0], center_y + crop_size // 2)
    data_cropped = data[y_start:y_end, x_start:x_end]
    return data_cropped
#%% Visualization of the cropped image
crop_size = 5000
data = fits.getdata(file)
data_mean = np.mean(data)
data_std = np.std(data)
data_cropped = crop_image(data, data.shape[1]//2, data.shape[0]//2, crop_size)
data_c_mean = np.mean(data_cropped)
data_c_std = np.std(data_cropped)
fig, axes = plt.subplots(2, figsize = (30,20))
axes[0].imshow(data, vmin = data_mean-data_std, vmax = data_mean + data_std)
square = patches.Rectangle(((data.shape[1]//2)-crop_size//2, (data.shape[0]//2)-crop_size//2), crop_size, crop_size, linewidth=3, edgecolor='r', facecolor='none')
axes[0].add_patch(square)
axes[1].imshow(data_cropped, vmin = data_mean-data_std, vmax = data_mean + data_std)
#%%
def calc_norm_variance(array):
    mean = np.mean(array)
    variance = np.sum((np.array(array) - mean)**2)
    FM = 1/(array.shape[0]*array.shape[1]) * variance / mean
    return FM
#%%
all_FM = []
all_fwhm = []
crop_size = 2000
source_size = 30
focusposlist = []
all_fwhm_error = []
for file in files:
    
    start = time.perf_counter()
    data = np.array(fits.getdata(file), dtype = float)
    #hdr = fits.getheader(file)
    data_cropped = crop_image(data, data.shape[1]//2, data.shape[0]//2, crop_size)
    mean, median, std = sigma_clipped_stats(data_cropped, sigma=3.0)
    data_cropped -= median
    threshold = 30 * std
    fwhm_x_all = []
    fwhm_y_all = []
    from astropy.convolution import convolve
    from photutils.segmentation import make_2dgaussian_kernel
    kernel = make_2dgaussian_kernel(3.0, size=5)  # FWHM = 3.0
    #convolved_data = convolve(data_cropped, kernel)
    segment_map = detect_sources(data_cropped, threshold, npixels=10)
    #focusposlist.append(hdr['FOCUSPOS'])
    print(time.perf_counter() - start)

    start = time.perf_counter()
    data = np.array(fits.getdata(file), dtype = float)
    data_cropped = crop_image(data, data.shape[1]//2, data.shape[0]//2, crop_size)
    data_cropped = np.ascontiguousarray(data_cropped)
    bkg = sep.Background(data_cropped)
    data_sub = data_cropped - bkg
    objects = sep.extract(data_sub, 30, err=bkg.globalrms, segmentation_map = False)
    bkg_image = bkg.back()
    print(time.perf_counter() - start)
    plt.imshow(bkg_image, interpolation='nearest', cmap='gray', origin='lower')
    plt.colorbar();
    from astropy.table import Table
    sources = Table(objects)
#%%
sources = sources[sources['flag']==0]
plt.scatter(sources['a'],sources['b'], alpha = 0.3)
#%%
from matplotlib.patches import Ellipse

# plot background-subtracted image

fig, ax = plt.subplots(figsize = (20,20))
m, s = np.mean(data_sub), np.std(data_sub)
im = ax.imshow(data_sub, interpolation='nearest', cmap='gray',
               vmin=m-s, vmax=m+s, origin='lower')

# plot an ellipse for each object
for i in range(len(sources)):
    e = Ellipse(xy=(sources['x'][i], sources['y'][i]),
                width=6*sources['a'][i],
                height=6*sources['b'][i],
                angle=sources['theta'][i] * 180. / np.pi)
    e.set_facecolor('none')
    e.set_edgecolor('red')
    ax.add_artist(e)
#%%
    
from matplotlib.patches import Ellipse

# plot background-subtracted image
fig, ax = plt.subplots()
m, s = np.mean(data_sub), np.std(data_sub)
im = ax.imshow(data_sub, interpolation='nearest', cmap='gray',
               vmin=m-s, vmax=m+s, origin='lower')

# plot an ellipse for each object
for i in range(len(objects)):
    e = Ellipse(xy=(objects['x'][i], objects['y'][i]),
                width=6*objects['a'][i],
                height=6*objects['b'][i],
                angle=objects['theta'][i] * 180. / np.pi)
    e.set_facecolor('none')
    e.set_edgecolor('red')
    ax.add_artist(e)
    
    
    FM = 0
    for bbox in segment_map.bbox:
        source_segment  = crop_image(data_cropped, round(bbox.center[1]), round(bbox.center[0]), crop_size = np.max(bbox.shape)+10)
        convolved_source = convolve(source_segment, kernel)

        #plt.imshow(source_segment, vmax = 30, vmin = 0)
        #plt.show()
        FM += calc_norm_variance(source_segment)
        ##############
        #gauss_init = models.Gaussian2D(amplitude=np.max(source_segment),
        #                                x_mean=(np.max(bbox.shape)+10)//2, y_mean=(np.max(bbox.shape)+10)//2)
        #fitter = fitting.LevMarLSQFitter()
        #x, y = np.meshgrid(np.arange(0, len(source_segment[0,:]), 1), np.arange(0, len(source_segment[:,0]), 1))
        #gauss_fit = fitter(gauss_init, x,y, source_segment)
        #fwhm_x = 2 * np.sqrt(2 * np.log(2)) * gauss_fit.x_stddev.value
        #fwhm_y = 2 * np.sqrt(2 * np.log(2)) * gauss_fit.y_stddev.value
        #fwhm_x_all.append(fwhm_x)
        #fwhm_y_all.append(fwhm_y)
        # Project onto 1D arrays for x and y directions
        projection_x = np.sum(source_segment, axis=0)  # Sum along the y-axis
        projection_y = np.sum(source_segment, axis=1)  # Sum along the x-axis
        # Fit Gaussian to the projections
        def gaussian_fit(data, axis_values):
            g_init = models.Gaussian1D(amplitude=data.max(), mean=axis_values[np.argmax(data)], stddev=1.0)
            fit_p = fitting.LevMarLSQFitter()
            gaussian_fit = fit_p(g_init, axis_values, data)
            return gaussian_fit
        x = np.linspace(-5, 5, len(projection_x))
        y = np.linspace(-5, 5, len(projection_y))
        fit_x = gaussian_fit(projection_x, x)
        fit_y = gaussian_fit(projection_y, y)
        fwhm_x = 2 * np.sqrt(2 * np.log(2)) * fit_x.stddev.value
        fwhm_y = 2 * np.sqrt(2 * np.log(2)) * fit_y.stddev.value
        fwhm_x_all.append(fwhm_x)
        fwhm_y_all.append(fwhm_y)
        
        
    # 여기에 Gaussian fitting (2D or 1D) 추가하기 with error
    ##############
    all_FM.append(FM)
    fwhm_x_all_clipped = sigma_clip(fwhm_x_all, sigma_lower = 1, sigma_upper = 1, maxiters = 3, cenfunc = 'median', stdfunc = 'mad_std', masked = False)
    fwhm_y_all_clipped = sigma_clip(fwhm_y_all, sigma_lower = 1, sigma_upper = 1, maxiters = 3, cenfunc = 'median', stdfunc = 'mad_std', masked = False)
    fwhm_mean = (np.median(fwhm_x_all_clipped) + np.median(fwhm_y_all_clipped))/2
    from scipy.stats import median_abs_deviation
    from astropy.stats import mad_std
    all_fwhm_error.append(np.sqrt(median_abs_deviation(fwhm_x_all_clipped)**2 + median_abs_deviation(fwhm_y_all_clipped)**2))
    all_fwhm.append(fwhm_mean)
    
    #all_fwhm_error.append(np.sqrt(np.std(fwhm_x_all_clipped)**2 + np.std(fwhm_y_all_clipped)**2))
    
#%%
plt.imshow(convolved_data, vmin = data_c_mean-data_c_std, vmax = data_c_mean + data_c_std)
plt.colorbar()
#%%
plt.imshow(data_cropped, vmin = data_c_mean-data_c_std, vmax = data_c_mean + data_c_std)
plt.colorbar()
#%%
fig, ax1 = plt.subplots()
ax2 = ax1.twinx()
# Plot the first scatter plot on the left y-axis (ax1)
ax1.scatter(focusposlist, all_FM, color='blue', label='Focus Meature (FM)')
ax1.set_xlabel('X-axis')
ax1.set_ylabel('Y-axis 1', color='blue')
ax1.tick_params('y', colors='blue')
# Plot the second scatter plot on the right y-axis (ax2)
ax2.scatter(focusposlist, all_fwhm, facecolor = 'none', edgecolor ='red', label='FWHM')
ax2.errorbar(focusposlist, all_fwhm, all_fwhm_error, fmt = 'none', ecolor ='k')
ax2.set_ylim(0, 5)
ax2.set_ylabel('Y-axis 2', color='red')
ax2.tick_params('y', colors='red')

# Display the legend for both scatter plots
ax1.legend(loc='upper left')
ax2.legend(loc='upper right')

# %%
plt.plot(fwhm_y_all)
# %%
focusposlist[22]
# %%
all_FM[22]
# %%
