"""
:module: wyrm.util.feature_extraction
:auth: Nathan T Stevens
:email: ntsteven (at) uw.edu
:org: Pacific Northwest Seismic Network
:license: AGPL-3.0
:purpose: Provide extension of obspy.signal.trigger module
          methods for pick onset probability predictions from
          ML models (e.g., EQTransformer; Mousavi et al., 2020)
          assuming peaks generally take the form of an normal
          distribution
"""
import numpy as np
from obspy import UTCDateTime
from obspy.signal.trigger import trigger_onset
from pandas import DataFrame
from scipy.optimize import leastsq
# from scipy.special import erf, erfc


def expandable_trigger(pred_trace, pthr=0.2, ethr=0.01, ndata_bounds=[15, 9e99], oob_delete=True):
    charfct = pred_trace.data
    # Based on obspy.signal.trigger.trigger_onset
    t_main = trigger_onset(
        charfct,
        pthr,
        pthr,
        max_length=max(ndata_bounds),
        max_len_delete=oob_delete)
    t_exp = trigger_onset(
        charfct,
        ethr,
        ethr,
        max_length=max(ndata_bounds),
        max_len_delete=oob_delete)
    
    passing_triggers = []
    # Iterate across triggers
    for mtrig in t_main:
        mi0 = mtrig[0]
        mi1 = mtrig[1]
        for etrig in t_exp:
            ei0 = etrig[0]
            ei1 = etrig[1]
            # If expanded trigger is, or contains main trigger
            if ei0 <= mi0 < mi1 <= ei1:
                # If delete bool is True and expanded trigger is too small, pass
                if oob_delete and ei1 - ei0 < min(ndata_bounds):
                    pass
                # in all other cases, append
                else:
                    passing_triggers.append(etrig)
    passing_triggers = np.array(passing_triggers, dtype=np.int64)
    return passing_triggers
    
def triggers_to_time(triggers, t0, dt):
    times = np.full(shape=triggers.shape, fill_value=t0)
    times += triggers*dt
    return times

        



##########################################
# Methods for estimating statistics from #
# y = f(x) representations of histograms #
##########################################


def est_curve_quantiles(x, y, q=[0.16, 0.5, 0.84]):
    """
    Approximate the quantiles of a evenly binned population
    represented as a discrete y = f(x) using the following
    formulation:

    i = argmin(abs(q - cumsum(y)/sum(y)))
    x[i]

    cumsum and sum are called as
    numpy.nancumsum & numpy.nansum to strengthen method
    against numpy.nan values.

    :: INPUTS ::
    :param x: [array-like] independent parameter
    :param y: [array-like] dependent parameter
                        values y[i] stand as frequency proxy
                        for values x[i]
    :param q: [array-like] quantiles to calculate with
                        q \in [0,1]
    :: OUTPUT ::
    :return qx: [(len(q),) numpy.ndarray]
                        Approximated quantile values sourced
                        from values of x[i]
    :return qy: [(len(q),) numpy.ndarray]
                        Probability values corresponding to
                        approximated quantile values
    """
    if 0.5 not in q:
        q.append(0.5)
    q.sort
    csy = np.nancumsum(y)
    sy = np.nansum(y)
    qx = np.array([x[np.argmin(np.abs(_q - csy / sy))] for _q in q])
    qy = np.array([y[np.argmin(np.abs(_q - csy / sy))] for _q in q])
    return qx, qy


def est_curve_normal_stats(x, y, fisher=False, dtype=np.float32):
    """
    Estimate the mean and standard deviation of a population represented
    by a discrete, evenly sampled function y = f(x), using y as weights
    and x as population bins.

    Estimates are made as the weighted mean
    and the weighted standard deviation:
    https://www.itl.nist.gov/div898/software/dataplot/refman2/ch2/weightsd.pdf

    Estimates of skewness and kurtosis are made using the 
    weighted formulation for the 3rd and 4th moments described here:
    https://www.mathworks.com/matlabcentral/answers/10058-skewness-and-kurtosis-of-a-weighted-distribution

    :: INPUTS ::
    :param x: [array-like] independent variable values (population bins)
    :param y: [array-like] dependent variable values (weights)
    :param fisher:
    :param dtype: [type] output type formatting
                    default is numpy.float32
    :: OUTPUTS ::
    :return est_mean: [dtype] y-weighted mean estimate
    :return est_std:  [dtype] y-weighted std estimate
    :return est_skew: [dtype] y-weighted skewness estimate
    :return est_kurt: [dtype] y-weighted kurtosis estimate
    """
    if ~isinstance(x, np.ndarray):
        try:
            x = np.array(x)
        except:
            raise TypeError
    elif x.dtype != dtype:
        x = x.astype(dtype)
    if ~isinstance(y, np.ndarray):
        try:
            y = np.array(y)
        except:
            raise TypeError
    elif y.dtype != dtype:
        y = y.astype(dtype)

    # Remove the unweighted mean (perhaps redundant)
    dx = x - np.nanmean(x)
    # Calculate y-weigted mean of delta-X values
    dmean = np.nansum(dx * y) / np.nansum(y)
    # Then add the unweighted mean back in
    est_mean = dmean + np.nanmean(x)

    # Calculate the y-weighted standard deviation of delta-X values
    # Compose elements
    # Numerator
    std_num = np.nansum(y * (dx - dmean) ** 2)
    # N-prime: number of non-zero (finite) weights
    Np = len(y[(y > 0) & (np.isfinite(y))])
    # Denominator
    std_den = (Np - 1.0) * np.nansum(y) / Np
    # Compose full expression for y-weighted std
    est_std = np.sqrt(std_num / std_den)

    # Calculate weighted 3rd moment
    wm3 = np.nansum(y * (dx - dmean) ** 3.0) / np.nansum(y)
    # And weighted skewness
    est_skew = wm3 / est_std**3.0

    # Calculate weighted 4th moment
    wm4 = np.nansum(y * (dx - dmean) ** 4.0) / np.nansum(y)
    # And weighted kurtosis
    est_kurt = wm4 / est_std**4.0
    if fisher:
        est_kurt -= 3.0

    # Calculate weighted 4th moment (kurtosis)
    return dtype(est_mean), dtype(est_std), dtype(est_skew), dtype(est_kurt)


def process_est_prediction_stats(
    prediction_trace,
    thr=0.1,
    extra_quantiles=[0.05, 0.2, 0.3, 0.7, 0.8, 0.95],
    pad_sec=0.05,
    ndata_bounds=[15, 9e99],
):
    """
    Run triggering with a uniform threshold on prediction traces and extract a set of gaussian and quantile
    statistical representations of prediction probability peaks that exceed the trigger threshold

    :: INPUTS ::
    :param prediction_trace:    [obspy.core.trace.Trace]
        Trace containing phase onset prediction probability timeseries data
    :param thr:              [float] trigger-ON/-OFF threshold value
    :param pad_sec:             [float]
        amount of padding on either side of data bounded by trigger ON/OFF
        times for for including additional, marginal population samples
        for estimating gaussian and quantile statistics
    :param extra_quantiles: [list of float]
        Additional quantiles to assess beyond Q1 (q = .25), Q3 (q = .75), and median (q = .5)
    :param ndata_bounds:    [2-tuple of int]
        minimum & maximum count of data for each trigger window
    :param quantiles:       [list of float]
        quantile values to assess within a trigger window under assumptions
        stated in documentation of est_curve_quantiles()
    :: OUTPUT ::
    :return df_out:     [pandas.dataframe.DataFrame]
        DataFrame containing the following metrics for each trigger:
            'et_on'     Epoch ON trigger time
            'et_off'    Epoch OFF trigger time
            'et_max'    Epoch max probability time
            'p_max'     Max probability value
            'et_mean'   Epoch mean probability time
            'p_mean'    Mean probability value
            'dt_std'    Delta time standard deviation [seconds]
            'skew'      Estimated skewness of probability distribution
            'kurt'      Estimated kurtosis of probability distribution
            'pdata'     Number of data used for statistical measures
            'et_med'    Epoch median probability time
            'p_med'     Median probability value
            'dt_q1'     Delta time for 1st Quartile (0.25 quantile)
                            relative to et_med: et_q1 - et_med
            'dt_q3'     Delta time for 3rd Quartile (0.75 quantile)
                            relative to et_med: et_q3 - et_med
            f'dt_q{extra_quantiles:.2f}'
                        Delta time(s) for extra_quantiles
                            relative to et_med: et_q{} - et_med
    """
    # create dictionary holder for triggers


    # Define default statistics for each trigger
    cols = [
        "et_on",
        "et_off",
        "et_max",
        "p_max",
        "et_mean",
        "p_mean",
        "dt_std",
        "skew",
        "kurt",
        "pdata",
        "et_med",
        "p_med",
        "dt_q1",
        "dt_q3",
    ]
    # Define default quantiles
    quants = [0.025, 0.159, 0.5, 0.84, 0.975]
    # Get epoch time vector from trace
    times = prediction_trace.times(type="timestamp")
    preds = prediction_trace.data
    # Get pick indices with Obspy builtin method
    triggers = trigger_onset(
        preds,
        thr,
        thr,
        max_len=ndata_bounds[1],
        max_len_delete=True,
    )
    # Append extra_quantiles
    if isinstance(extra_quantiles, float):
        quants += [extra_quantiles]
        cols += [f"dt_q{extra_quantiles:.2f}"]
    elif isinstance(extra_quantiles, list):
        quants += extra_quantiles
        cols += [f"dt_q{_eq:.2f}" for _eq in extra_quantiles]

    # Iterate across triggers to extract statistics
    holder = []
    for _trigger in triggers:
        # Get trigger ON and OFF timestamps
        _t0 = times[_trigger[0]]
        _t1 = times[_trigger[1]]
        # Get windowed data for statistical estimation
        ind = (times >= _t0 - pad_sec) & (times <= _t1 + pad_sec)
        _times = times[ind]
        _preds = preds[ind]
        # Run gaussian statistics
        et_mean, dt_std, skew, kurt = est_curve_normal_stats(_times, _preds)
        p_mean = _preds[np.argmin(np.abs(et_mean - _times))]
        # Run quantiles
        et_q, p_q = est_curve_quantiles(_times, _preds, q=quants)
        line = [
            _t0,
            _t1,
            _times[np.argmax(_preds)],
            np.max(_preds),
            et_mean,
            p_mean,
            dt_std,
            skew,
            kurt,
            len(_times),
            et_q[0],
            p_q[0],
            et_q[1] - et_q[0],
            et_q[2] - et_q[0],
        ]
        # Add extra quantiles if provided
        if len(et_q) > 3:
            line += [_et - et_q[0] for _et in et_q[3:]]
        # Append trigger statistics to holder
        holder.append(line)
    try:
        df_out = DataFrame(holder, columns=cols)
    except:
        breakpoint()

    return df_out


############################################
# Methods for writing results to EarthWorm #
############################################


def _pick_quality_mapping(
    X, grade_max=(0.02, 0.03, 0.04, 0.05, np.inf), dtype=np.int32
):
    """
    Provide a mapping function between a continuous parameter X
    and a discrete set of grade bins defined by their upper bounds

    :: INPUTS ::
    :param X: [float] input parameter
    :param grade_max: [5-tuple] monotonitcally increasing set of
                    values that provide upper bounding values for
                    a set of bins
    :param dtype: [type-assignment method] default nunpy.int32
                    type formatting to assign to output

    :: OUTPUT ::
    :return grade: [dtype value] grade assigned to value

    """
    # Provide sanity check that INF is included as the last upper bound
    if grade_max[-1] < np.inf:
        grade_max.append(np.inf)
    for _i, _g in enumerate(grade_max):
        if X <= _g:
            grade = dtype(_i)
            break
        else:
            grade = np.nan
    return grade


def ml_prob_models_to_PICK2K_msg(
    feature_dataframe,
    pick_metric="et_mean",
    std_metric="et_std",
    qual_metric="",
    m_type=255,
    mod_id=123,
    org_id=1,
    seq_no=0,
):
    """
    Convert ml pick probability models into Earthworm PICK2K formatted
    message strings
    -- FIELDS --
    1.  INT Message Type (1-255)
    2.  INT Module ID that produced this message: codes 1-255 signifying, e.g., pick_ew, PhaseWorm
    3.  INT Originating installation ID (1-255)
    4.  Intentional 1 blank (i.e., ‘ ‘)
    5.  INT Sequence # assigned by picker (0-9999). Key to associate with coda info.
    6.  Intentional 1 blank
    7.  STR Site code (left justified)
    8.  STR Network code (left justified)
    9.  STR Component code (left justified)
    10. STR Polarity of first break
    11. INT Assigned pick quality (0-4)
    12. 2 blanks OR space for phase assignment (i.e., default is ‘  ‘)
    13. INT Year
    14. INT Month
    15. INT Day
    16. INT Hour
    17. INT Minute
    18. INT Second
    19. INT Millisecond
    20. INT Amplitude of 1st peak after arrival (counts?)
    21. INT Amplitude of 2nd peak after arrival
    22. INT Amplitude of 3rd peak after arrival
    23. Newline character

    """
    msg_list = []
    for _i in range(len(feature_dataframe)):
        _f_series = feature_dataframe.iloc[_i, :]
        grade = _pick_quality_mapping(_f_series[qual_metric])
        # Fields 1, 2, 3, 4
        fstring = f"{m_type:3d}{mod_id:3d}{org_id:3d} "
        # Fields 5 - 8
        fstring += f"{seq_no:4d} {_f_series.sta:-5s}{_f_series.net:-2s}"
        fstring += f"{_f_series.cha:-3s} "
        # Fields 10 -
        # fstring += f' {}
        msg_list.append(fstring)

    return msg_list


########################################################
# Methods for fitting normal pdfs to probability peaks #
########################################################


def scaled_normal_pdf(p, x):
    """
    Model a scaled normal distribution (Gaussian)
    with parameters:
    p[0] = A       - Amplitude of the distribution
    p[1] = mu      - Mean of the distribution
    p[2] = sigma   - Standard deviation of the distribution

    for sample locations x
    """
    y = p[0] * np.exp(-0.5 * ((x - p[1]) / p[2]) ** 2)
    return y


def normal_pdf_error(p, x, y_obs):
    """
    Calculate the misfit between an offset normal distribution (Gaussian)
    with parameters:
    p[0] = A       - Amplitude of the distribution
    p[1] = mu      - Mean of the distribution
    p[2] = sigma   - Standard deviation of the distribution

    and X, y_obs data that may

    :: INPUTS ::
    :param p: [array-like] see above
    :param x: [array-like] independent variable, sample locations
    :param y_obs: [array-like] dependent variable at sample locations

    :: OUTPUT ::
    :return y_err: [array-like] misfit calculated as y_obs - y_cal
    """
    # Calculate the modeled y-values given positions x and parameters p[:]
    y_cal = scaled_normal_pdf(p, x)
    y_err = y_obs - y_cal
    return y_err


def fit_probability_peak(prediction_trace, fit_thr_coef=0.1, mindata=30, p0=None):
    """
    Fit a normal distribution to an isolated peak in a phase arrival prediction trace from
    a phase picking/detection ML prediction in SeisBench formats.

    Fitting of the normal distribution is conducted using scipy.optimize.leastsq()
    and the supporting method `normal_pdf_error()` included in this module.

    :: INPUTS ::
    :param prediction_trace: [obspy.core.trace.Trace]
                                Trace object windowed to contain a single prediction peak
                                with relevant metadata
    :param obs_utcdatetime:  [datetime.datetime] or [None]
                                Optional reference datetime to compare maximum probability
                                timing for calculating delta_t. This generally is used
                                for an analyst pick time.
    :param treshold_coef:    [float]
                                Threshold scaling value for the maximum data value used to
                                isolating samples for fitting the normal distribution
    :param mindata:           [int]
                                Minimum number of data requred for extracting features
    :param p0:                [array-like]
                                Initial normal distribution fit values
                                Default is None, which assumes
                                - amplitude = nanmax(data),
                                - mean = mean(epoch_times where data >= threshold)
                                - std = 0.25*domain(epoch_times where data >= threshold)

    :: OUTPUTS ::
    :return amp:            [float] amplitude of the model distribution
                                IF ndata < mindata --> this is the maximum value observed
    :return mean:           [float] mean of the model distribution in epoch time
                                IF ndata < mindata --> this is the timestamp of the maximum observed value
    :return std:            [float] standard deviation of the model distribution in seconds
                                IF ndata < mindata --> np.nan
    :return cov:            [numpy.ndarray] 3,3 covariance matrix for <amp, mean, std>
                                IF ndata < mindata --> np.ones(3,3)*np.nan
    :return err:            [float] L-2 norm of data-model residuals
                                IF ndata < mindata --> np.nan
    :return ndata:          [int] number of data used for model fitting
                                IF ndata < mindata --> ndata
    """
    # Get data
    data = prediction_trace.data
    # Get thresholded index
    ind = data >= fit_thr_coef * np.nanmax(data)
    # Get epoch times of data
    d_epoch = prediction_trace.times(type="timestamp")
    # Ensure there are enough data for normal distribution fitting
    if sum(ind) >= mindata:
        x_vals = d_epoch[ind]
        y_vals = data[ind]
        # If no initial parameter values are provided by user, use default formula
        if p0 is None:
            p0 = [
                np.nanmax(y_vals),
                np.nanmean(x_vals),
                0.25 * (np.nanmax(x_vals) - np.nanmin(x_vals)),
            ]
        outs = leastsq(normal_pdf_error, p0, args=(x_vals, y_vals), full_output=True)
        amp, mean, std = outs[0]
        cov = outs[1]
        err = np.linalg.norm(normal_pdf_error(outs[0], x_vals, y_vals))

        return amp, mean, std, cov, err, sum(ind)

    else:
        return (
            np.nanmax(data),
            float(d_epoch[np.argwhere(data == np.nanmax(data))]),
            np.nan,
            np.ones((3, 3)) * np.nan,
            np.nan,
            sum(ind),
        )


def process_predictions(
    prediction_trace,
    et_obs=None,
    thr_on=0.1,
    thr_off=0.1,
    fit_pad_sec=0.1,
    fit_thr_coef=0.1,
    ndata_bounds=[30, 9e99],
    quantiles=[0.25, 0.5, 0.75],
):
    """
    Extract statistical fits of normal distributions to prediction peaks from
    ML prediction traces that trigger above a specified threshold.

    :: INPUTS ::
    :param prediction_trace:    [obspy.core.trace.Trace]
        Trace containing phase onset prediction probability timeseries data
    :param et_obs:              [None or list of epoch times]
        Observed pick times in epoch time (timestamps) associated with the
        station/phase-type for `prediction_trace`
    :param thr_on:              [float] trigger-ON threshold value
    :param thr_off:             [float] trigger-OFF threshold value
    :param fit_pad_sec:         [float]
        amount of padding on either side of data bounded by trigger ON/OFF
        times for calculating Gaussian fits to the probability peak(s)
    :param fit_thr_coef:    [float] Gaussian fit data
    :param ndata_bounds:    [2-tuple of int]
        minimum & maximum count of data for each trigger window
    :param quantiles:       [list of float]
        quantile values to assess within a trigger window under assumptions
        stated in documentation of est_curve_quantiles()
    :: OUTPUT ::
    :return df_out:     [pandas.dataframe.DataFrame]
        DataFrame containing the following metrics for each trigger
        and observed pick:
        'et_on'     - Trigger onset time [epoch]
        'et_off'    - Trigger termination time [epoch]
        'p_scale'   - Probability scale from Gaussian fit model \in [0,1]
        'q_scale'   - Probability value at the estimated median (q = 0.5)
        'm_scale'   - Maximum estimated probability value
        'et_mean'   - Expectation peak time from Gaussian fit model [epoch]
        'et_max'    - timestamp of the maximum probability [epoch]
        'det_obs_prob' - delta time [seconds] of observed et_obs[i] - et_max
                            Note: this will be np.nan if there are no picks in
                                  the trigger window
        'et_std'    - Standard deviation of Gaussian fit model [seconds]
        'L2 res'    - L2 norm of data - model residuals for Gaussian fit
        'ndata'     - number of data considered in the Gaussian model fit
        'C_pp'      - variance of model fit for p_scale
        'C_uu'      - variance of model fit for expectation peak time
        'C_oo'      - variance of model fit for standard deviation
        'C_pu'      - covariance of model fit for p & u
        'C_po'      - covariance of model fit for p & o
        'C_uo'      - covariance of model fit for u & o
    """
    # Define output column names
    cols = [
        "et_on",
        "et_off",
        "p_scale",
        "q_scale",
        "m_scale",
        "et_mean",
        "et_med",
        "et_max",
        "det_obs_prob",
        "et_std",
        "L2 res",
        "ndata",
        "C_pp",
        "C_uu",
        "C_oo",
        "C_pu",
        "C_po",
        "C_uo",
    ]
    # Ensure median is included in quantiles
    quantiles = list(quantiles)
    med_ind = None
    for _i, _q in enumerate(quantiles):
        if _q == 0.5:
            med_ind = _i
    if med_ind is None:
        quantiles.append(0.5)
        med_ind = -1

    cols += [f"q{_q:.2f}" for _q in quantiles]
    # Get pick indices with Obspy builtin method
    triggers = trigger_onset(
        prediction_trace.data,
        thr_on,
        thr_off,
        max_len=ndata_bounds[1],
        max_len_delete=True,
    )
    times = prediction_trace.times(type="timestamp")
    # Iterate across triggers:
    feature_holder = []
    for _trigger in triggers:
        _t0 = times[_trigger[0]]
        _t1 = times[_trigger[1]]
        # If there are observed time picks provided, search for picks
        wind_obs = []
        if isinstance(et_obs, list):
            for _obs in et_obs:
                if _t0 <= _obs <= _t1:
                    wind_obs.append(_obs)
        _tr = prediction_trace.copy().trim(
            starttime=UTCDateTime(_t0) - fit_pad_sec,
            endtime=UTCDateTime(_t1) + fit_pad_sec,
        )
        # Conduct gaussian fit
        outs = fit_probability_peak(
            _tr, fit_thr_coef=fit_thr_coef, mindata=ndata_bounds[0]
        )
        # Get timestamp of maximum observed data
        et_max = _tr.times(type="timestamp")[np.argmax(_tr.data)]

        # Get times of quantiles:
        qet, qmed, q = est_curve_quantiles(
            _tr.times(type="timestamp"), _tr.data, q=quantiles
        )

        # Iterate across observed times, if provided
        # First handle the null
        if len(wind_obs) == 0:
            _det_obs_prob = np.nan
            feature_line = [
                _t0,
                _t1,
                outs[0],
                outs[1],
                et_max,
                _det_obs_prob,
                outs[2],
                outs[4],
                outs[5],
                outs[3][0, 0],
                outs[3][1, 1],
                outs[3][2, 2],
                outs[3][0, 1],
                outs[3][0, 2],
                outs[3][1, 2],
            ]
            if quantiles:
                feature_line += list(qet)
            feature_holder.append(feature_line)
        # Otherwise produce one line with each delta time calculation
        elif len(wind_obs) > 0:
            for _wo in wind_obs:
                _det_obs_prob = _wo - et_max
                feature_line = [
                    _t0,
                    _t1,
                    outs[0],
                    outs[1],
                    et_max,
                    _det_obs_prob,
                    outs[2],
                    outs[4],
                    outs[5],
                    outs[3][0, 0],
                    outs[3][1, 1],
                    outs[3][2, 2],
                    outs[3][0, 1],
                    outs[3][0, 2],
                    outs[3][1, 2],
                ]
                if quantiles:
                    feature_line += list(qouts)

                feature_holder.append(feature_line)

    df_out = DataFrame(feature_holder, columns=cols)
    return df_out