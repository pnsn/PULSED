"""
:module: Tracker.py
:auth: Nathan T. Stevens
:email: ntsteven (at) uw.edu
:org: Pacific Northwest Seismic Network
:purpose: This module contains the Tracker class used to pre-process
          post-process, and book-keep event-based streaming waveform
          data for near-real-time ML prediction for a single given
          instrument (1-3 orthogonal data channels) at a given seismic
          station. 
"""
import os
import sys
import torch
import numpy as np
from time import time
from copy import deepcopy
from obspy import Stream, Trace, read, UTCDateTime
# Buried dependency - see Tracker.snuffle()
# from pyrocko import obspy_compat

sys.path.append("..")
import core.preprocessing as prep
import core.postprocessing as post


# class PredStreamTracker(Stream):


#     def __init__(self, prep_stream=None, model=None):
#         # Bring in everything obspy.core.stream.Stream has to offer!
#         super().__init__()
#         self.


def _get_example_waveforms():
    file = os.path.join(
        "..", "data", "test_dataset_1", "UW", "GNW", "UW.GNW..BH?.2017.131.00.mseed"
    )
    stream = read(file, fmt="MSEED")
    return stream


def example_config():
    """
    Example of the config argument required for PredictionEngine() instantiation
    This dictionary consists of ordered keys that indicate the

    """
    config = {
        "order_raw": {"order": "Z3N1E2", "merge_kwargs": {"method": 1}},
        "filter": {"ftype": "bandpass", "freqmin": 0.05, "freqmax": 45},
        "homogenize": {
            "samp_rate": 100,
            "interp_kwargs": {"method": "weighted_average_slopes", "no_filter": False},
            "resamp_kwargs": {"window": "hann", "no_filter": False},
            "trim_method": "max",
        },
        "window": {
            "npts_window": 6000,
            "npts_step": 3000,
            "detrend_type": "linear",
            "chan_fill_method": "zero_pad",
            "fill_value": 0.0,
            "flush_streams": False,
        },
        "normalize": {"method": "max"},
        "taper": {"npts_taper": 6},
        "stack": {
            "npts_window": 6000,
            "npts_step": 3000,
            "npts_blind": 500,
            "method": "max",
        },
    }
    return config


"""
(Major?) overhaul on Tracker needed for I/O with PyEarthworm
Tracker needs (and conveniently should) know the InstID for each SNCL
relevant to a particular seismometer at a particular site.

E.g., GNW.UW may have InstID's
    GNW.UW.ENZ.. = 1003
    GNW.UW.ENN.. = 1004
    GNW.UW.ENE.. = 1005
    
    And we want to pull data from the main ring (RingID = 1000, typically)
    so we can immediately use an ordered list of these InstIDs to do the 
    book-keeping and channel sorting for us at jump.

    Then, for a given configuration, we can also tell the tracker which ring
    it should be submitting results to (e.g., RingID = 1005, receiving pick messages)


    The updated Tracker is likely going to be someting a 
    super.__init__(EWModule)
    or have multiple calls of EWModule.add_ring
    able to host a flexible number of connections to
    the WAVE ring at the time of initializing a particular `tracker` object
    e.g.,
    tracker = Tracker(wavering_ID = 1000, instID={'Z': 1003, 'N': 1004, 'E': 1005}, ...)

    class Tracker:
            def __init__:
                self.wavering_ID = wavering_ID
                self.module_ID = module_ID
                self.inst_IDs = inst_ID
                self._used_inst_IDs = []
                self._inst_conn_IDs = {}
                self.in_mods = {}
                self.out_mods = {}
                self.ew_config = {'Tpulse': 30., 'debug': False}
                ...
                and the rest of the python-ey stuff
                ...
            
                
            def connect_tracker_to_ew(self, verbose=True):
                # Ensure connection is only called once
                if len(self.in_mods) < len(self._used_inst_IDs):
                    for _i ,_k in enumerate(self.inst_IDs):
                        if self.inst_IDs[_k] not in self._used_instIDs:
                            wave_ring_module = PyEW.EWModule(self.wavering_ID, self.module_ID, self.inst_IDs[_k], self.ew_config['Tpulse'], self.ew_config['debug'])
                            self.in_mods.update{_k:wave_ring_module}
                            self._used_instIDs.append(self.inst_IDs[_k])
                            self._inst_conn_IDs.update{_k: _i}
                        else:
                            if verbose:
                                print(f'inst ID {inst_IDs[_k]} appears to be in use already, skipping re-connect attempt')

            def start_streaming(self, pipeline, dtype=None):
                # WHILE RUNNING 
                st = Stream()
                # LOAD STREAM
                for _k in self.inst_IDs.keys():
                    _wave = self.inst_IDs[_k].get_wave(self._inst_conn_IDs[_k]))                
                    _tr = wyrm.util.PyEW_translate.pyew_tracebuff2_to_trace(_wave, dtype=dtype)
                    st += _tr
                # DO PIPELINE

                # SOMETHING SOMETHING WAIT FOR Tpulse SEC AND RUN AGAIN....????

"""


class Tracker:
    """
    This class provides a structured pre-processing and post-processing object for
    waveform data and continuous prediction outputs from a machine learning model
    at the granularity of a single seismic instrument: i.e., 1-C or 3-C data

    :: INPUTS ::
    :param raw_stream: [obspy.core.stream.Stream]
                Stream object that is either empty or contains data from a single
                seismic instrument with 1-3 channels where the only difference in
                SNCL codes between traces are the 3rd character in the channel name
                (SEED component code)
    :param config: [dict of dicts]
                Dictionary containing a script for pre-processing sequencing as keys
                and dictionaries in the primar value positions that are passed as 
                class-method arguments via the **value syntax.

    :: ATTRIBUTES ::
    ++ PUBLIC ++
    :attr name:         [str] SNCL name of instrument
    
    :attr SNCL:         [dict] explicit dictionary of SNCL name elements

    :attr raw_stream:   [obspy.core.stream.Stream] 
                        unaltered waveform data used as a reference/back-up
                        in-memory data packet from which pre-processing steps start.
                        Sequential uses of the tracker re-introduce data fragments
                        saved in self._last_raw_stream (see below). There is a single
                        class-method that acts on data held in self.raw_stream:
                        see:    self.order_raw()

    :attr prep_stream:  [obspy.core.stream.Stream]
                        progressively altered waveform data subject to preprocessing
                        class-methods.
                        see:    self.filter()
                                self.homogenize()
                                self.window() [input]

    :attr windows:      [(mwindows, 3, npts_window) numpy.ndarray]
                        array of windowed data that are subject to further preprocessing
                        class-methods.
                        see:    self.window()
                                self.normalize()
                                self.taper()

    :attr predictions:  [(mwindows, 3, npts_window) numpy.ndarray]
                        array of windowed, modeled values (ML "predictions") received from
                        a segmented ML output. 

    :attr pred_stream:  [obspy.core.stream.Stream]
                        contains traces of merged prediction windows output from ML prediction
                        operations with header information scraped from the following attributes.
                            self._ref_t0 - starttime
                            self._last_raw_stream - trace.stats template
                            self._resamp_rate - sampling_rate
                            self._last_prediction_window - continuity of iterative predicitons
    ~~ BUFFER ~~
    :attr _last_raw_stream:         [obspy.core.stream.Stream]
                                    Stream containing raw data corresponding to the
                                    last window generated, plus any trailing data that were
                                    residual due to an insufficient amount to form a full window
                                    Attribute is populated near the end of class-method
                                    window() and the data are coppied to raw_stream when new
                                    data are ingested.

    :attr _last_prediction_window:  [(1, 3, _npts_window) numpy.ndarray]
                                    the last prediction window (prediction[-1, :, :]) from the
                                    previous call of prediction_to_stream(). See class-method
                                    prediciton_to_stream() for more information.

    -- PRIVATE --
    :attr _config:      [dict] (private) see INPUTS

    :attr _resamp_rate: [int32] (private) 
                        resampling rate to apply to all data
                    TODO: provide an enforcement rule in self.homogenize() that 
                          over-rules a user-passed argument?

    :attr _npts_window: [int32] (private) 
                        window length in number of points for windows passed to ML prediction routines. 
                    NOTE: this parameter is method-specific, e.g.,
                            EQTransoformer: 6000
                            PhaseNet: 3000

    :attr _npts_step:   [int32] (private)
                        window stride length (complement to overlap) for successive
                        windows passed to ML prediciton routines
                    NOTE: must be less than _npts_window by a value

    :attr _ref_t0:      [time.timestamp]  (private)
                        epoch starttime of the most recently ingested  waveform 
                        data packet.
                    TODO: need to build in clearer update rules
    """

    def __init__(self, raw_stream=Stream(), config=example_config()):
        # Metadata attributes
        self.name = None
        self.SNCL = None
        self._config = config
        self._resamp_rate = None
        self._npts_window = None
        self._npts_step = None
        self._raw_tags = []
        self._prep_tags = []
        self._window_tags = []
        # Buffers
        self._ref_t0 = None
        self._last_raw_stream = Stream()
        self._last_prediction_window = None

        # Streams attributes
        self.raw_stream = raw_stream
        self.prep_stream = Stream()
        self.pred_stream = Stream()

        # Numpy ndarray attributes
        self.windows = None
        self.predictions = None

        # If a stream is provided, scrape metadata for SNCL and _ref_t0
        if isinstance(raw_stream, (Stream, Trace)):
            if isinstance(raw_stream, Trace):
                self.raw_stream = Stream(self.raw_stream)
            if len(self.raw_stream) > 0:
                SNCL_list = []
                t0_list = []
                for _tr in self.raw_stream:
                    t0_list.append(_tr.stats.starttime)
                    net = self.raw_stream[0].stats.network
                    sta = self.raw_stream[0].stats.station
                    loc = self.raw_stream[0].stats.location
                    cha = f"{self.raw_stream[0].stats.channel[:2]}?"
                    if (sta, net, cha, loc) not in SNCL_list:
                        SNCL_list.append((sta, net, cha, loc))
                if len(SNCL_list) == 1:
                    self.SNCL = dict(
                        zip(
                            ["station", "network", "channel", "location"],
                            [sta, net, cha, loc],
                        )
                    )
                    self.name = ".".join(list(self.SNCL.values()))
                    self._ref_t0 = np.min(t0_list)
                elif len(SNCL_list) == 0:
                    pass
                else:
                    print(f"Multiple ({len(SNCL_list)}) SNCL combinations detected!")

    def __repr__(self):
        # Show Name
        repr = f"Tracker: {self.name}\n"
        # Conditionally show sampling information
        if isinstance(self._resamp_rate, (float, int)):
            repr += f"Resamp_Rate:  {self._resamp_rate:4d} sps\n"
        if isinstance(self._npts_window, int):
            repr += f"Npts_Window: {self._npts_window:5d} samples\n"
        if isinstance(self._npts_step, int):
            repr += f"Npts_Step:   {self._npts_step:5d} samples\n"
        # Show Buffer contents
        repr += "~~~ buffer ~~~\n"
        repr += f"-ref t0-\n{self._ref_t0}\n"
        repr += f"-raw-\n{self._last_raw_stream}\n"
        repr += f"-pred-\n{self._last_prediction_window}\n"
        # Show raw data
        repr += "=== raw data ===\n"
        repr += f"{self.raw_stream}\n"
        repr += f"tags: {self._raw_tags}\n"
        # Conditionally show preprocessed data
        if len(self.prep_stream) > 0:
            repr += "=== preprocess ===\n"
            repr += f"{self.prep_stream}\n"
            repr += f"tags: {self._prep_tags}\n"
        # Conditionally show shape of windows
        if isinstance(self.windows, np.ndarray):
            repr += "=== windows ===\n"
            repr += f"shape: {self.windows.shape}\n"
            repr += f"tags: {self._window_tags}\n"
            # TODO: add some log of applied processing steps
        if isinstance(self.predictions, np.ndarray):
            repr += "=== preds ===\n"
            repr += f"shape: {self.predictions.shape}\n"
            if isinstance(self.pred_stream, Stream):
                repr += f"{self.pred_stream}\n"

        # repr += "=== config ===\n"
        # repr += f"{self._config}\n"
        return repr

    def copy(self):
        """
        Return a deepcopy of the InstrumentPredictionTracker
        """
        return deepcopy(self)

    def reset_prep(self):
        """
        Reset self.prep_stream to a copy of self.raw_stream
        """
        self.prep_stream = self.raw_stream.copy()


    

    def order_raw(self, order="Z3N1E2", merge_kwargs={"method": 1}):
        """
        Merge and order traces into a vertical, horizontal1, horizontal2 order,
        with specified merge_kwargs for obspy.stream.Stream.merge().

        Acts in-place on self.raw_stream

        :: INPUTS ::
        :param order: [str]
                        Order of channel codes. Generally shouldn't change
                        from the default
        :param merge_kwargs: [dict]
                        key-word-arguments for obspy.stream.Stream.merge()

        :: OUTPUT ::
        No output, results in merged, ordered self.raw_stream if successful
        """
        # Create holder stream
        _stream = Stream()
        # Iterate across channel codes from order
        for _c in order:
            # Subset data and merge from raw_stream
            _st = self.raw_stream.select(channel=f"??{_c}").copy().merge(**merge_kwargs)
            # if subset stream is now one stream, add to holder stream
            if len(_st) == 1:
                _stream += _st
        # Overwrite raw
        self.raw_stream = _stream
        self._raw_tags.append('ordered')
        return None

    def filter(self, ftype, from_raw=True, **kwargs):
        """
        Filter data using obspy.core.stream.Stream.filter() class-method
        with added option of data source

        :: INPUTS ::
        :param ftype: [string]
                `type` argument for obspy.core.stream.Stream.filter()
        :param from_raw: [bool]
                True = copy self.raw_stream and filter the copy
                False = filter self.prep_stream in-place
        :param **kwargs: [kwargs]
                kwargs to pass to obspy.core.stream.Stream.filter()

        """
        if from_raw:
            _st = self.raw_stream.copy()
        else:
            _st = self.prep_stream
        self.prep_stream = _st.filter(ftype, **kwargs)
        if from_raw:
            self._prep_tags = self._raw_tags
        self._prep_tags.append('filter')

    def homogenize(
        self,
        samp_rate,
        interp_kwargs={"method": "weighted_average_slopes", "no_filter": False},
        resamp_kwargs={"window": "hann", "no_filter": False},
        trim_method="max",
        from_raw=False,
    ):
        """
        Resample waveform data using ObsPy methods for a specified
        target `samp_rate` using Trace.interpolate() to upsample and
        Trace.resample() to downsample.

        :: INPUTS ::
        :param samp_rate: [int-like] target sampling rate
        :param interp_kwargs: [dict]
                        key-word-arguments to pass to Trace.interpolate()
                        for upsampling
        :param resamp_kwargs: [dict]
                        key-word-arguments to pass to Trace.resample()
                        for downsampling
        :param trim_method: [string] or [None]
                        None: apply no padding
                        'max': trim to earliest starttime and latest endtime
                               contained in source stream
                        'min': trim to latest starttime and earliest endtime
                               contained in source stream
                        'med': trim to median starttime and endtime contained
                               in source stream
        :param from_raw: [BOOL]
                        Should data be sourced from self.raw_stream?
                        False --> source from self.prep_stream
        :: OUTPUT ::
        No outputs. Updated data are written to self.prep_stream
        """
        if from_raw:
            _st = self.raw_stream.copy()
        elif ~from_raw and isinstance(self.prep_stream, Stream):
            _st = self.prep_stream
        else:
            print(f"self.prep_stream is {type(self.prep_stream)} -- invalid")
            return None
        ts_list = []
        te_list = []
        for _tr in _st:
            ts_list.append(_tr.stats.starttime.timestamp)
            te_list.append(_tr.stats.endtime.timestamp)
            if _tr.stats.sampling_rate < samp_rate:
                _tr.interpolate(samp_rate, **interp_kwargs)
            elif _tr.stats.sampling_rate > samp_rate:
                _tr.resample(samp_rate, **resamp_kwargs)

        if trim_method is not None:
            # Minimum valid window
            if trim_method in ["min", "Min", "MIN", "minimum", "Minimum", "MINIMUM"]:
                # Save trimmed segment without padding to self._last_raw_stream
                self._last_raw_stream += _st.copy().trim(
                    starttime=UTCDateTime(np.nanmin(te_list))
                )
                # Trim segment
                _st = _st.trim(
                    starttime=UTCDateTime(np.nanmax(ts_list)),
                    endtime=UTCDateTime(np.nanmin(te_list)),
                    pad=True,
                )
            # Maximum window
            elif trim_method in ["max", "Max", "MAX", "maximum", "Maximum", "MAXIMUM"]:
                # Trim and pad
                _st = _st.trim(
                    starttime=UTCDateTime(np.nanmin(ts_list)),
                    endtime=UTCDateTime(np.nanmax(te_list)),
                    pad=True,
                )
            # Median-defined window
            elif trim_method in ["med", "Med", "MED", "median", "Median", "MEDIAN"]:
                # Save trimmed segment without padding to self._last_raw_stream
                self._last_raw_stream += _st.copy().trim(
                    starttime=UTCDateTime(np.nanmedian(te_list))
                )
                # Trim segment
                _st = _st.trim(
                    starttime=UTCDateTime(np.nanmedian(ts_list)),
                    endtime=UTCDateTime(np.nanmedian(te_list)),
                    pad=True,
                )
            else:
                print(f"Invalid value for trim_method {trim_method}")
        # Update prep_stream
        self.prep_stream = _st
        self._resamp_rate = samp_rate
        if from_raw:
            self._prep_tags = self._raw_tags
        self._prep_tags.append('homogenized')
        return None

    def window(
        self,
        npts_window=6000,
        npts_step=3000,
        detrend_type="linear",
        chan_fill_method="zero_pad",
        fill_value=0,
        flush_streams=False,
        **options,
    ):
        """
        Convert preprocessed stream into a 3-D numpy array consisting of detrended,
        data windows.

        This version of the window class-method uses obspy methods for detrending.

        This routine assumes the traces in self.prep_stream have already been
        trimmed to uniform npts lengths.

        Calling this method also saves a trimmed version of self.raw_stream
        to self._last_raw_stream that corresponds to the last window produced
        and any trailing data values.

        :: INPUTS ::
        :param npts_window: [int] number of data per window
        :param npts_step: [int] number of data per window advance
        :param detrend_type: [str] method used for detrending trace data
                    once it has been trimmed.
                    See obspy.core.trace.Trace.detrend().
                    If a given trace has masked data, detrending is conducted 
                    with the following sequence:
                    detrended = _tr.copy().split().detrend(detrend_type).merge(method=1)
        :param chan_fill_method: [str] method for handling missing channels
                    'zero_pad' - missing channels remain 0-vectors
                            (e.g., Ni et al., 2023)
                    'clone' - missing channels are cloned from existing
                        channels.
                        If 1C (vertical only), vertical channel data are
                        copied to both horizontals 
                            (e.g., Retailleau et al., 2021).
                        If there is a dead horizontal channel, then the live
                        horizontal channel is cloned.
        :param fill_value: [numpy.float32] fill value for masked elements in
                    self.prep_stream
        :param flush_streams: [bool]
                    True - erase data from:
                                self.raw_stream
                                self.prep_stream
                           to reclaim space on memory
                    False - do not erase data (default)
        :param **options: Collects keyword argments which are passed to the selected
                    detrend function. See obspy.core.trace.Trace.detrend() documentation.

        :: OUTPUTS ::
        :assign windows: populate/overwrite the `windows` attribute
        :assign _last_raw_stream: populate/overwrite the `_last_raw_stream` attribute
        :assign last_t0: [obspy.core.utcdatetime.UTCDateTime]
                        populate/update attribute with the UTCDateTime of the first
        :output success: [bool]
                        if 1+ windows are generated, return True
                        else, return False
        """
        if ~isinstance(fill_value, np.float32):
            fill_value = np.float32(fill_value)
        # Get metadata from prep_stream
        # Number of data
        npts_data = self.prep_stream[0].stats.npts
        if npts_data >= npts_window:
            # Sampling rate
            sr_data = self.prep_stream[0].stats.sampling_rate
            # Starttime timestamp
            T0 = self.prep_stream[0].stats.starttime
            # Window length in seconds
            sec_window = (npts_window - 1) / sr_data
            # Window step in seconds
            sec_step = npts_step / sr_data
            # Get the number of complete windows
            nwin = (npts_data - npts_window) // npts_step + 1
            # Create windows holder
            windows = np.zeros(shape=(nwin, 3, npts_window), dtype=np.float32)
            # Iterate across windows:
            # breakpoint()
            for _n, _st in enumerate(
                self.prep_stream.slide(sec_window, sec_step, include_partial_windows=False)
            ):
                if _n < nwin:
                    # Create holder stream
                    _st2 = _st.copy()
                    # Iterate across traces in slide generated _stream to preserve channel order
                    for _i, _tr in enumerate(_st2):
                        # Handle masked streams
                        if np.ma.is_masked(_tr.data):
                            # Remove masked elements, detrend, and re-merge to Trace
                            _tr = (
                                _tr.split()
                                .detrend(type=detrend_type, **options)
                                .merge(fill_value=fill_value)[0]
                            )
                            # Re-enforce original time bounds in the event of lateral padding
                            _tr.trim(
                                starttime=_st[0].stats.starttime,
                                endtime=_st[0].stats.endtime,
                                pad=True,
                            )
                        # Do standard approach otherwise
                        else:
                            _tr.detrend(type=detrend_type, **options)

                        # Pull data vector
                        _data = _tr.data
                        # If data are masked, (re)apply fill_value
                        if np.ma.is_masked(_data):
                            _data.fill_value = fill_value
                            # If so, use fill_value
                            _data = np.ma.filled(_st[0].data.data)
                        # And assign vector to windows
                        windows[_n, _i, :] = _data

                    # Catch case where length of _st is less than 3
                    if _i < 2:
                        # If zero_pad, do nothing
                        if chan_fill_method.casefold() in ["zero_pad", "zero"]:
                            pass
                        # If clone (after Retailleau et al., 2021)
                        # NOTE: This formulation will clone Z data to both horizontals
                        # if
                        elif chan_fill_method.casefold() in ["clone", "duplicate"]:
                            for _in in np.arange(_i + 1, 3):
                                windows[_n, _i, :] = _data

            # Update object attributes
            self.windows = windows
            self._last_t0 = T0
            self._npts_window = npts_window
            self._npts_step = npts_step
            self._last_raw_stream = self.raw_stream.copy().trim(starttime=_tr.stats.starttime)
            self._window_tags.append('generated')
            successful = True
            # Clear stream attributes if specified
            if flush_streams:
                self.raw_stream = self.last_raw_stream.copy()
                self.prep_stream = Stream()
        else:
            successful = False
        return successful

    def normalize(self, method="max"):
        """
        Normalize windows contained in self.windows, operating in-place,
        using finite elements of each window to calculate a normalizing
        factor

        :: INPUTS ::
        :param method: [str]
                    'max': normalize windows using the maximum magnitude of
                           finite values within a given window
                           uses window /= nanmax(abs(window))
                    'std': normalize windows using the standard deviation
                           of finite values within a given window
                           uses window /= nanstd(window)
                    NOTE: If an invalid `method` is provided, no change occurs
                        and class-method terminates
        :: OUTPUTS ::
        :update windows: update self.windows with normalized version
        """
        if method.casefold() == "max":
            self.windows /= np.nanmax(np.abs(self.windows), axis=-1, keepdims=True)
            self._window_tags.append('max scaled')
        elif method.casefold() == "std":
            self.windows /= np.nanstd(self.windows, axis=-1, keepdims=True)
            self._window_tags.append('std scaled')
        else:
            pass
        return self.windows

    def taper(self, npts_taper=6):
        """
        Taper self.windows using a cosine taper of specified sample length,
        operating in-place

        :: INPUTS ::
        :param npts_taper: [int] number of samples on either side of window
                        to apply taper

        :: OUTPUT ::
        :update windows: update self.windows with tapered version
        :return windows: [numpy.ndarray] tapered windows
        """
        taper = 0.5 * (1.0 + np.cos(np.linspace(np.pi, 2.0 * np.pi, npts_taper)))
        self.windows[:, :, :npts_taper] *= taper
        self.windows[:, :, -npts_taper:] *= taper[::-1]
        self._window_tags.append('tapered')
        return self.windows

    def apply_config(self, config=None, verbose=False):
        """
        Apply sequential processing steps specified by
        self._config with the general expression:

        eval(self._key(**self._config[_key]))
        
        with the option to overwrite the self._config attribute

        :: INPUTS ::
        :param config: [dict] or None
                if None: use self._config for sequencing
                otherwise, overwrite self._config and attempt to proceed
        :param verbose: [bool]
                True: Print updates on processing steps and elapsed times
                False: run silent
        :: OUTPUT ::
        :update <sequential>: updates to Tracker attributes depend on form of 
                self._config
        """
        t0 = time()
        if config is not None:
            self._config = config
        for _k in self._config.keys():
            try:
                eval(f"self.{_k}(**self._config[_k])")
                if verbose:
                    print(f"self.{_k}() complete (ET: {time() - t0:.3f} sec)")
            except AttributeError:
                if verbose:
                    print(f"key '{_k}' not recognized, skipping")
        if verbose:
            print(f"COMPLETE (ET: {time() - t0:.3f} sec)")


    def __to_prep__(self):
        """
        Convenience method for copying self.raw_stream to
        self.prep_stream
        """
        self.prep_stream = self.raw_stream.copy()

    def output_windows(self, astensor=True):
        """
        Return self.windows with the option as formatting
        as a torch.Tensor and write last last window to
        the self.last_window attribute

        :: INPUTS ::
        :param astensor: [BOOL]
                should the output be a torch.Tensor?
                False = output numpy.ndarray
        :: OUTPUT ::
        :return self.windows:
        """
        if isinstance(self.windows, np.array):
            self.last_window = self.windows[-1, :, :]
            if astensor:
                return torch.Tensor(self.windows)
            else:
                return self.windows
        else:
            return None

    ###########################
    # POST PROCESSING METHODS #
    ###########################
    def ingest_predictions(self, predictions):
        if isinstance(self._last_prediction_window, np.ndarray):
            self.predictions = predictions
            
            
            
            
            self._last_prediction_window = predictions[-1, :, :]



    def prediction_to_traces(self):


    ####################
    # PLOTTING METHODS #
    ####################
    def _prep_comparison_stream(self):
        _st = Stream()
        if isinstance(self.raw_stream, Stream) and len(self.raw_stream) > 0:
            _str = self.raw_stream.copy()
            for _tr in _str:
                _tr.stats.location = "(r)"
                _st += _tr
        if isinstance(self.prep_stream, Stream) and len(self.prep_stream) > 0:
            _stp = self.prep_stream.copy()
            for _tr in _stp:
                _tr.stats.location = "(p)"
                _st += _tr
        if isinstance(self.pred_stream, Stream) and len(self.pred_stream) > 0:
            _stx = self.pred_stream.copy()
            for _tr in _stx:
                _st += _tr
        return _st

    def plot(self, *args, **kwargs):
        """
        Use Obspy Plotting utilties to visualize contents of a Tracker

        Plot a temporary copy of contents of self.raw_stream and
        self.prep_stream with appended channel codes (r) and (p)
        respectively. Uses the syntax of obspy.core.stream.Stream.plot()

        :: INPUTS ::
        :param *args: Gather positional arguments to pass to Stream.plot()
        :param **kwargs: Gather key-word arguments to pass to Stream.plot()

        :: OUTPUT ::
        :return outs: Standard output from Stream.plot()
        """
        _st = self._prep_comparison_stream()

        outs = _st.sort(keys=["channel"], reverse=True).plot(*args, **kwargs)
        return outs

    def _snuffle(self, *args, **kwargs):
        """
        Use Pyrocko Plotting utilities to visualize contents of a Tracker

        Provide a way to view Stream-formatted contents of a Tracker
        using the pyrocko.obspy_compat extension to Stream class-methods
        Stream.snuffle().

        Runs 
            from pyrocko import obspy_compat
            obspy_compat.plant() 
        if Stream.snuffle() returns AttributeError.

        :: INPUTS ::
        :param *args: Collect positional arguments for Stream.snuffle()
        :param **kwargs: Collect key-word arguments for Stream.snuffle()

        :: OUTPUT ::
        :return outs: Return standard out of Stream.snuffle()
        """
        _st = self._prep_comparison_stream()
        try:
            outs = _st.snuffle(*args, **kwargs)
        except AttributeError:
            from pyrocko import obspy_compat
            obspy_compat.plant()
            outs = _st.snuffle(*args, **kwargs)
        return outs


    # ################################
    # # POSTPROCESSING CLASS-METHODS #
    # ################################

    # def ingest_preds(self, preds, merge_method='max'):
    #     """
    #     Receive numpy.ndarray of windowed predictions and merge into
    #     """
    #     _widx = self.windex
    #     _mod = self.model
    #     # Conduct merge from predictions to stack
    #     stack = post._restructure_predictions(
    #         preds,
    #         _widx,
    #         _mod,
    #         merge_method=merge_method
    #     )

    #     #

    #     # Get index of last prediction (from a temporal standpoint)
    #     _lw = np.argmax(windex)
    #     # (over)write self.last_pred
    #     self.last_pred = preds[_lw, :, :]

    # def preps_to_disk(self, loc, fmt='MSEED'):
    #     """
    #     Write pre-procesed stream to disk
    #     """

    # def preds_to_disk(self, loc, fmt='MSEED'):
    #     """
    #     Write prediction traces to disk
    #     """


#     #########################
#     # PRIVATE CLASS-METHODS #
#     #########################

#     def __update_lasts_prep__(self):
#         """
#         Update self.last_window_raw and self.last_window
#         """

#     def __update_last_window_raw__(self):
#         """

#         """

#     def __update_last_window__(self):

#     def __update_last_pred__(self):


#     def __flush_waveforms__(self):
#         """
#         Clear out self.raw_waveforms and move
#         self.last_window_raw to self.raw_waveforms
#         to preserve
#         """
#         if isinstance(self.last_window_raw, Stream):

#     def __flush_predictions__(self):


# def default_pp_kwargs():
#     interp_kwargs = {'method': 'average_weighted_slopes', 'no_filter': False}
#     resamp_kwargs = {'window': 'hann', 'no_filter': False}


# class PredictionEngine:

#     def __init__(self, config, trackers=None, model=None, device=None, waveform_pp_kwargs=default_pp_kwargs(), ):

#         self.trackers = dict(zip([f'{x.stats.network}.{x.stats.station}.{x.stats.location}.{x.stats.bandinst}' for x in stations],
#                                     instruments))
#         self.model = model
#         self.device = device
#         self.tensor = None
#         self.swindex = None
#         self.config = config
#         self.resample_kwargs = resample_kwargs
#         self.windowing_kwargs = windowing_kwargs

#     def __repr__(self):
#         return list(self.stations.keys())


#     # def __add__(self, other):
#     #     """
#     #     Add two PredictionTrackers or a PredictionTracker and
#     #     an InstrumentPredictionTracker

#     #     :param other: [PredictionTracker] or [InstrumentPredictionTracker]
#     #     """
#     #     if isinstance(other, InstrumentPredictionTracker):
#     #         other =

#     def copy(self):
#         """
#         Create a deepcopy of the PredictionTracker object
#         """
#         return deepcopy(self)


#     def run_preprocessing(self):
#         for _k in self.stations.keys():
#             self.stations[_k].


#     def aggregate_windows(self):


#     def batch_prediction(self):


#     def disaggregate_preds(self):
#         """
#         Disassemble prediction numpy.ndarray
#         into component parts and return them
#         to their respective InstrumentPredicionTracker's
#         contained within self.instruments
#         """


#     def ingest_new(self, stream):
#         """
#         Ingest new waveform data in obspy.core.stream.Stream format
#         and update data holdings within each relevant member of
#         """


#     def preds_to_disk()

#     def runall(self):
