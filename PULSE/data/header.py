"""
:module: PULSE.data.header
:auth: Nathan T. Stevens
:org: Pacific Northwest Seismic Network
:email: ntsteven (at) uw.edu
:license: AGPL-3.0
:purpose: This module holds class definitions for metadata header objects that build off the
    ObsPy :class:`~obspy.core.util.attribdict.AttribDict` and :class:`~obspy.core.trace.Stats` classes
    that are used for the following classes in :mod:`~PULSE`
     - :class:`~PULSE.data.mltrace.MLTrace` and decendents (:class:`~PULSE.data.mltracebuff.MLTraceBuff`) use :class`~PULSE.data.header.MLStats`
     - :class:`~PULSE.data.dictstream.DictStream` uses :class`~PULSE.data.header.DictStreamStats`
     - :class:`~PULSE.data.window.Window` uses :class`~PULSE.data.header.WindowStats`
     - :class:`~PULSE.mod.base.BaseMod` and decendents (i.e., all :mod:`~PULSE.mod` classes) uses :class`~PULSE.data.header.PulseStats`
     
"""
import copy
from obspy import UTCDateTime
from obspy.core.trace import Stats
from obspy.core.util.attribdict import AttribDict

###################################################################################
# Machine Learning Stats Class Definition #########################################
###################################################################################

class MLStats(Stats):
    """Extends the :class:`~obspy.core.mltrace.Stats` class to encapsulate additional metadata associated with machine learning enhanced time-series processing.

    Added/modified defaults are:
     - 'location' = '--'
     - 'model' - name of the ML model associated with a MLTrace
     - 'weight' - name of the ML model weights associated with a MLTrace

    :param header: initial non-default values with which to populate this MLStats object
    :type header: dict
    """
    # set of read only attrs
    readonly = ['endtime']
    # add additional default values to obspy.core.mltrace.Stats's defaults
    defaults = copy.deepcopy(Stats.defaults)
    defaults.update({
        'location': '--',
        'model': '',
        'weight': '',
        'processing': []
    })

    # dict of required types for certain attrs
    _types = copy.deepcopy(Stats._types)
    _types.update({
        'model': str,
        'weight': str
    })

    def __init__(self, header={}):
        """Create a :class:`~PULSE.data.mltrace.MLStats` object

        :param header: initial non-default values with which to populate this MLStats object
        :type header: dict
        """        
        super(Stats, self).__init__(header)
        if self.location == '':
            self.location = self.defaults['location']

    def __str__(self):
        """
        Return better readable string representation of this :class:`~PULSE.data.mltrace.MLStats` object.
        """
        prioritized_keys = ['model','weight','station','channel', 'location', 'network',
                          'starttime', 'endtime', 'sampling_rate', 'delta',
                          'npts', 'calib']
        return self._pretty_str(prioritized_keys)
    

###################################################################################
# Dictionary Stream Stats Class Definition ########################################
###################################################################################

class DictStreamStats(AttribDict):
    """A class to contain metadata for a :class:`~PULSE.data.dictstream.DictStream` object of the based on the
    ObsPy :class:`~obspy.core.util.attribdict.AttribDict` class and operates like the ObsPy :class:`~obspy.core.trace.Stats` class.
    
    This DictStream header object contains metadata on the minimum and maximum starttimes and endtimes of :class:`~PULSE.data.mltrace.MLTrace`
    objects contained within a :class:`~PULSE.data.dictstream.DictStream`, along with a Unix-wildcard-inclusive string representation of 
    all trace keys in **DictStream.traces** called **common_id**

    """
    defaults = {
        'common_id': '*',
        'min_starttime': None,
        'max_starttime': None,
        'min_endtime': None,
        'max_endtime': None,
        'processing': []
    }

    _types = {'common_id': str,
              'min_starttime': (type(None), UTCDateTime),
              'max_starttime': (type(None), UTCDateTime),
              'min_endtime': (type(None), UTCDateTime),
              'max_endtime': (type(None), UTCDateTime)}

    def __init__(self, header={}):
        """Initialize a DictStreamStats object

        A container for additional header information of a PULSE :class:`~PULSE.data.dictstream.DictStream` object


        :param header: Non-default key-value pairs to include with this DictStreamStats object, defaults to {}
        :type header: dict, optional
        """        
        super(DictStreamStats, self).__init__()
        self.update(header)
    
    def _pretty_str(self, priorized_keys=[], hidden_keys=[], min_label_length=16):
        """
        Return tidier string representation of this :class:`~PULSE.data.dictstream.DictStreamStats` object

        Based on the :meth:`~obspy.core.util.attribdict.AttribDict._pretty_str` method, and adds
        a `hidden_keys` argument

        :param priorized_keys: Keys of current AttribDict which will be
            shown before all other keywords. Those keywords must exists
            otherwise an exception will be raised. Defaults to [].
        :type priorized_keys: list, optional
        :param hidden_keys: Keys of current AttribDict that will be hidden, defaults to []
                        NOTE: does not supercede items in prioritized_keys.
        :param min_label_length: Minimum label length for keywords, defaults to 16.
        :type min_label_length: int, optional
        :return: String representation of object contents.
        """
        keys = list(self.keys())
        # determine longest key name for alignment of all items
        try:
            i = max(max([len(k) for k in keys]), min_label_length)
        except ValueError:
            # no keys
            return ""
        pattern = "%%%ds: %%s" % (i)
        # check if keys exist
        other_keys = [k for k in keys if k not in priorized_keys and k not in hidden_keys]
        # priorized keys first + all other keys
        keys = priorized_keys + sorted(other_keys)
        head = [pattern % (k, self.__dict__[k]) for k in keys]
        return "\n".join(head)


    def __str__(self):
        prioritized_keys = ['common_id',
                            'min_starttime',
                            'max_starttime',
                            'min_endtime',
                            'max_endtime',
                            'processing']
        return self._pretty_str(prioritized_keys)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))

    def update_time_range(self, trace):
        """
        Update the minimum and maximum starttime and endtime attributes of this :class:`~PULSE.data.dictstream.DictStreamStats` object using timing information from an obspy Trace-like object.

        :param trace: trace-like object with :attr:`stats` from which to query starttime and endtime information
        :type trace: obspy.core.trace.Trace
        """
        if self.min_starttime is None or self.min_starttime > trace.stats.starttime:
            self.min_starttime = trace.stats.starttime
        if self.max_starttime is None or self.max_starttime < trace.stats.starttime:
            self.max_starttime = trace.stats.starttime
        if self.min_endtime is None or self.min_endtime > trace.stats.endtime:
            self.min_endtime = trace.stats.endtime
        if self.max_endtime is None or self.max_endtime < trace.stats.endtime:
            self.max_endtime = trace.stats.endtime



###############################################################################
# WindowStats Class Definition ##########################################
###############################################################################

class WindowStats(DictStreamStats):
    """Child-class of :class:`~PULSE.data.dictstream.DictStreamStats` that extends
    contained metadata to include a set of reference values and metadata that inform
    pre-processing, carry metadata cross ML prediction operations using SeisBench 
    :class:`~seisbench.models.WaveformModel`-based models, and retain processing information
    on outputs of these predictions.

    :param header: collector for non-default values (i.e., not in WindowStats.defaults)
        to use when initializing a WindowStats object, defaults to {}
    :type header: dict, optional

    also see:
     - :class:`~PULSE.data.dictstream.DictStreamStats`
     - :class:`~obspy.core.util.attribdict.AttribDict`
    """    
    # NTS: Deepcopy is necessary to not overwrite _types and defaults for parent class
    _types = copy.deepcopy(DictStreamStats._types)
    _types.update({'ref_component': str,
                   'aliases': dict,
                   'thresholds': dict,
                   'reference_starttime': (UTCDateTime, type(None)),
                   'reference_npts': (int, type(None)),
                   'reference_sampling_rate': (float, type(None))})
    defaults = copy.deepcopy(DictStreamStats.defaults)
    defaults.update({'ref_component': 'Z',
                     'aliases': {'Z': 'Z3',
                                 'N': 'N1',
                                 'E': 'E2'},
                     'thresholds': {'ref': 0.95, 'other': 0.8},
                     'reference_starttime': None,
                     'reference_sampling_rate': None,
                     'reference_npts': None})
    
    def __init__(self, header={}):
        """Initialize a WindowStats object

        :param header: collector for non-default values (i.e., not in WindowStats.defaults)
            to use when initializing a WindowStats object, defaults to {}
        :type header: dict, optional

        also see:
         - :class:`~PULSE.data.dictstream.DictStreamStats`
         - :class:`~obspy.core.util.attribdict.AttribDict`
        """        
        # Initialize super + updates to class attributes
        super(WindowStats, self).__init__()
        # THEN update self with header inputs
        self.update(header)

    def __str__(self):
        prioritized_keys = ['ref_component',
                            'common_id',
                            'aliases',
                            'reference_starttime',
                            'reference_sampling_rate',
                            'reference_npts',
                            'processing']

        hidden_keys = ['min_starttime',
                       'max_starttime',
                       'min_endtime',
                       'max_endtime']

        return self._pretty_str(prioritized_keys, hidden_keys)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))

###############################
# PulseStats Class Definition #
###############################

class PulseStats(AttribDict):
    """A :class:`~obspy.core.util.attribdict.AttribDict` child-class for holding metadata
    from a given call of :meth:`~PULSE.mod.base.BaseMod.pulse`. 
    
    :var modname: name of the associated module
    :var starttime: POSIX start time of the last call of **pulse**
    :var endtime: UTC end time of the last call of **pulse**
    :var niter: number of iterations completed
    :var in0: input size at the start of the call
    :var in1: input size at the end of the call
    :var out0: output size at the start of the call
    :var out1: output size at the end of the call
    :var runtime: number of seconds it took for the call to run
    :var pulse rate: iterations per second
    :var stop: Reason iterations stopped

    Explanation of **stop** values
       - 'max' -- :meth:`~PULSE.mod.BaseMod.pulse` reached the **max_pulse_size** iteration limit
       - 'early0' -- flagged for early stopping before executing the unit-process in an iteration
       - 'early1' -- flagged for early stopping after executing the unit-process in an iteration
     """    
    readonly = ['pulse rate','runtime']
    _refresh_keys = {'starttime','endtime','niter'}
    defaults = {'modname': '',
                'starttime': 0,
                'endtime': 0,
                'stop': '',
                'niter': 0,
                'in0': 0,
                'in1': 0,
                'out0': 0,
                'out1': 0,
                'runtime':0,
                'pulse rate': 0}
    _types = {'modname': str,
              'starttime':float,
              'endtime':float,
              'stop': str,
              'niter':int,
              'in0':int,
              'in1':int,
              'out0':int,
              'out1':int,
              'runtime':float,
              'pulse rate':float}
    

    def __init__(self, header={}):
        """Create an empty :class:`~PULSE.mod.base.PulseStats` object"""
        super(PulseStats, self).__init__(header)

    def __setitem__(self, key, value):
        if key in self._refresh_keys:
            if key == 'starttime':
                value = float(value)
            elif key == 'endtime':
                value = float(value)
            elif key == 'niter':
                value = float(value)
            # Set current key
            super(PulseStats, self).__setitem__(key, value)
            # Set derived value: runtime
            self.__dict__['runtime'] = self.endtime - self.starttime
            # Set derived value: pulse rate
            if self.runtime > 0:
                self.__dict__['pulse rate'] = self.niter / self.runtime
            else:
                self.__dict__['pulse rate'] = 0.
            return
        if isinstance(value, dict):
            super(PulseStats, self).__setitem__(key, AttribDict(value))
        else:
            super(PulseStats, self).__setitem__(key, value)


    __setattr__ = __setitem__

    def __getitem__(self, key, default=None):
        return super(PulseStats, self).__getitem__(key, default)

    def __str__(self):
        prioritized_keys = ['modname','pulse rate','stop','niter',
                            'in0','in1','out0','out1',
                            'starttime','endtime','runtime']
        return self._pretty_str(priorized_keys=prioritized_keys)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))