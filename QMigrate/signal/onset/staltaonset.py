# -*- coding: utf-8 -*-
"""
The default onset function class - calculates STA/LTA onset (characteristic)
function from filtered seismic data.

"""

import numpy as np
from obspy.signal.invsim import cosine_taper
from obspy.signal.trigger import classic_sta_lta
from scipy.signal import butter, lfilter

import QMigrate.signal.onset.onset as qonset


def sta_lta_centred(a, nsta, nlta):
    """
    Calculates the ratio of the average signal in a short-term (signal) window
    to a preceding long-term (noise) window. STA/LTA value is assigned to the
    end of the LTA / start of the STA.

    Parameters
    ----------
    a : array-like
        Signal array

    nsta : int
        Number of samples in short-term window

    nlta : int
        Number of samples in long-term window

    Returns
    -------
    sta / lta : array-like
        Ratio of short term average to average in a preceding long term average
        window. STA/LTA value is assigned to end of LTA window / start of STA
        window -- "centred"

    """

    nsta = int(round(nsta))
    nlta = int(round(nlta))

    # Cumulative sum to calculate moving average
    sta = np.cumsum(a ** 2)
    sta = np.require(sta, dtype=np.float)
    lta = sta.copy()

    # Compute the STA and the LTA
    sta[nsta:] = sta[nsta:] - sta[:-nsta]
    sta[nsta:-nsta] = sta[nsta*2:]
    sta /= nsta

    lta[nlta:] = lta[nlta:] - lta[:-nlta]
    lta /= nlta

    sta[:(nlta - 1)] = 0
    sta[-nsta:] = 0

    # Avoid division by zero by setting zero values to tiny float
    dtiny = np.finfo(0.0).tiny
    idx = lta < dtiny
    lta[idx] = dtiny
    sta[idx] = 0.0

    return sta / lta


def onset(sig, stw, ltw, centred):
    """
    Calculate STA/LTA onset (characteristic) function from filtered seismic
    data.

    Parameters
    ----------
    sig : array-like
        Data signal used to generate an onset function

    stw : int
        Short term window length (# of samples)

    ltw : int
        Long term window length (# of samples)

    centred : bool, optional
        Compute centred STA/LTA (STA window is preceded by LTA window; value
        is assigned to end of LTA window / start of STA window) or classic
        STA/LTA (STA window is within LTA window; value is assigned to end of
        STA & LTA windows).

        Centred gives less phase-shifted (late) onset function, and is closer
        to a Gaussian approximation, but is far more sensitive to data with
        sharp offsets due to instrument failures. We recommend using classic
        for detect() and centred for locate() if your data quality allows it.
        This is the default behaviour; override by setting self.onset_centred.

    Returns
    -------
    onset : array-like
        log10(onset_raw) ; after clipping between -0.2 and infinity.

    """

    stw = int(round(stw))
    ltw = int(round(ltw))

    n_channels, n_samples = sig.shape
    onset = np.copy(sig)
    for i in range(n_channels):
        if np.sum(sig[i, :]) == 0.0:
            onset[i, :] = 0.0
        else:
            if centred is True:
                onset[i, :] = sta_lta_centred(sig[i, :], stw, ltw)
            else:
                onset[i, :] = classic_sta_lta(sig[i, :], stw, ltw)
            np.clip(1 + onset[i, :], 0.8, np.inf, onset[i, :])
            np.log(onset[i, :], onset[i, :])

    return onset


def filter(sig, sampling_rate, lc, hc, order=2):
    """
    Apply zero phase-shift Butterworth band-pass filter to seismic data.

    Parameters
    ----------
    sig : array-like
        Data signal to be filtered

    sampling_rate : int
        Number of samples per second, in Hz

    lc : float
        Lowpass frequency of band-pass filter

    hc : float
        Highpass frequency of band-pass filter

    order : int, optional
        Number of corners. NOTE: two-pass filter effectively doubles the
        number of corners.

    Returns
    -------
    fsig : array-like
        Filtered seismic data

    """

    # Construct butterworth band-pass filter
    b1, a1 = butter(order, [2.0 * lc / sampling_rate,
                            2.0 * hc / sampling_rate], btype="band")
    nchan, nsamp = sig.shape
    fsig = np.copy(sig)

    # Apply cosine taper then apply band-pass filter in both directions
    for ch in range(0, nchan):
        fsig[ch, :] = fsig[ch, :] - fsig[ch, 0]
        tap = cosine_taper(len(fsig[ch, :]), 0.1)
        fsig[ch, :] = fsig[ch, :] * tap
        fsig[ch, :] = lfilter(b1, a1, fsig[ch, ::-1])[::-1]
        fsig[ch, :] = lfilter(b1, a1, fsig[ch, :])

    return fsig


class ClassicSTALTAOnset(qonset.Onset):
    """
    QuakeMigrate default onset function class using a classic STA/LTA onset

    Attributes
    ----------
    p_bp_filter : array-like, [float, float, int]
        Butterworth bandpass filter specification
        [lowpass, highpass, corners*]
        *NOTE: two-pass filter effectively doubles the number of corners.

    s_bp_filter : array-like, [float, float, int]
        Butterworth bandpass filter specification
        [lowpass, highpass, corners*]
        *NOTE: two-pass filter effectively doubles the number of corners.

    p_onset_win : array-like, floats
        P onset window parameters
        [STA, LTA]

    s_onset_win : array-like, floats
        S onset window parameters
        [STA, LTA]

    pre_pad : float, optional
        Option to override the default pre-pad duration of data to read
        before computing 4d coalescence in detect() and locate(). Default
        value is calculated from the onset function durations.

    onset_centred : bool, optional
        Compute centred STA/LTA (STA window is preceded by LTA window;
        value is assigned to end of LTA window / start of STA window) or
        classic STA/LTA (STA window is within LTA window; value is assigned
        to end of STA & LTA windows).

        Centred gives less phase-shifted (late) onset function, and is
        closer to a Gaussian approximation, but is far more sensitive to
        data with sharp offsets due to instrument failures. We recommend
        using classic for detect() and centred for locate() if your data
        quality allows it. This is the default behaviour; override by
        setting this variable.


    Methods
    -------
    p_onset()
        Generate an onset function that represents the P-phase arrival

    s_onset()
        Generate an onset function that represents the S-phase arrival

    """

    def __init__(self, sampling_rate):
        """
        Class initialisation method.

        Parameters
        ----------
        sampling_rate : int
            Desired sampling rate for input data; sampling rate that detect()
            and locate() will be computed at.

        """

        super().__init__()

        self.sampling_rate = sampling_rate

        # Default filter parameters
        self.p_bp_filter = [2.0, 16.0, 2]
        self.s_bp_filter = [2.0, 12.0, 2]

        # Default onset window parameters
        self.p_onset_win = [0.2, 1.0]
        self.s_onset_win = [0.2, 1.0]

        # Onset position override
        self.onset_centred = False

    def __str__(self):
        """
        Return short summary string of the Onset object

        It will provide information on all of the various parameters that the
        user can/has set.

        """

        out = "\tOnset parameters"
        if self.onset_centred:
            out += " - using the centred STA/LTA onset\n"
        else:
            out += " - using the classic STA/LTA onset\n"
        out += "\t\tData sampling rate = {}\n\n"
        out += "\t\tBandpass filter P  = [{}, {}, {}]\n"
        out += "\t\tBandpass filter S  = [{}, {}, {}]\n\n"
        out += "\t\tOnset P [STA, LTA] = [{}, {}]\n"
        out += "\t\tOnset S [STA, LTA] = [{}, {}]\n\n"
        out = out.format(
            self.sampling_rate,
            self.p_bp_filter[0], self.p_bp_filter[1], self.p_bp_filter[2],
            self.s_bp_filter[0], self.s_bp_filter[1], self.s_bp_filter[2],
            self.p_onset_win[0], self.p_onset_win[1],
            self.s_onset_win[0], self.s_onset_win[1])

        return out

    def p_onset(self):
        """
        Generates an onset (characteristic) function for the P-phase from the
        Z-component signal.

        Parameters
        ----------
        sig_z : array-like
            Z-component time-series data

        sampling_rate : int
            Sampling rate in hertz

        Returns
        -------

        p_onset : array-like
            Onset function generated from log10(STA/LTA) of vertical
            component data

        """

        stw, ltw = self.p_onset_win
        stw = int(stw * self.sampling_rate) + 1
        ltw = int(ltw * self.sampling_rate) + 1

        lc, hc, ord_ = self.p_bp_filter
        self.filt_sigz = filter(self.sigz, self.sampling_rate, lc, hc, ord_)

        p_onset = onset(self.filt_sigz, stw, ltw, centred=self.onset_centred)

        return p_onset

    def s_onset(self):
        """
        Generates an onset (characteristic) function for the S-phase from the
        E- and N-components signal.

        Parameters
        ----------
        sig_e : array-like
            E-component time-series

        sig_n : array-like
            N-component time-series

        sampling_rate : int
            Sampling rate in hertz

        Returns
        -------
        s_onset_raw : array-like
            Onset function generated from raw STA/LTA of horizontal component
            data

        s_onset : array-like
            Onset function generated from log10(STA/LTA) of horizontal
            component data

        """

        stw, ltw = self.s_onset_win
        stw = int(stw * self.sampling_rate) + 1
        ltw = int(ltw * self.sampling_rate) + 1

        lc, hc, ord_ = self.s_bp_filter
        self.filt_sige = filter(self.sige, self.sampling_rate, lc, hc, ord_)
        self.filt_sign = filter(self.sign, self.sampling_rate, lc, hc, ord_)

        s_e_onset = onset(self.filt_sige, stw, ltw, centred=self.onset_centred)
        s_n_onset = onset(self.filt_sign, stw, ltw, centred=self.onset_centred)

        s_onset = np.sqrt((s_e_onset ** 2 + s_n_onset ** 2) / 2.)

        return s_onset

    @property
    def pre_pad(self):
        """Pre-pad is determined as a function of the onset windows"""
        pre_pad = max(self.p_onset_win[1], self.s_onset_win[1]) \
            + 3 * max(self.p_onset_win[0], self.s_onset_win[0])

        return pre_pad

    @pre_pad.setter
    def pre_pad(self, value):
        """Setter for pre-pad"""

        self._pre_pad = value

    @property
    def post_pad(self):
        """
        Post-pad is determined as a function of the max traveltime in the
        grid and the onset windows

        """

        return self._post_pad

    @post_pad.setter
    def post_pad(self, ttmax):
        """
        Define post-pad as a function of the maximum travel-time between a
        station and a grid point plus the LTA (in case onset_centred is True)

        """

        lta_max = max(self.p_onset_win[1], self.s_onset_win[1])
        self._post_pad = np.ceil(ttmax + 2 * lta_max)


class CentredSTALTAOnset(ClassicSTALTAOnset):
    """
    QuakeMigrate default onset function class using a centred STA/LTA onset

    Attributes
    ----------
    p_bp_filter : array-like, [float, float, int]
        Butterworth bandpass filter specification
        [lowpass, highpass, corners*]
        *NOTE: two-pass filter effectively doubles the number of corners.

    s_bp_filter : array-like, [float, float, int]
        Butterworth bandpass filter specification
        [lowpass, highpass, corners*]
        *NOTE: two-pass filter effectively doubles the number of corners.

    p_onset_win : array-like, floats
        P onset window parameters
        [STA, LTA]

    s_onset_win : array-like, floats
        S onset window parameters
        [STA, LTA]

    pre_pad : float, optional
        Option to override the default pre-pad duration of data to read
        before computing 4d coalescence in detect() and locate(). Default
        value is calculated from the onset function durations.

    onset_centred : bool, optional
        Compute centred STA/LTA (STA window is preceded by LTA window;
        value is assigned to end of LTA window / start of STA window) or
        classic STA/LTA (STA window is within LTA window; value is assigned
        to end of STA & LTA windows).

        Centred gives less phase-shifted (late) onset function, and is
        closer to a Gaussian approximation, but is far more sensitive to
        data with sharp offsets due to instrument failures. We recommend
        using classic for detect() and centred for locate() if your data
        quality allows it. This is the default behaviour; override by
        setting this variable.


    Methods
    -------
    p_onset()
        Generate an onset function that represents the P-phase arrival

    s_onset()
        Generate an onset function that represents the S-phase arrival

    """

    def __init__(self, sampling_rate):
        """
        Class initialisation method.

        Parameters
        ----------
        sampling_rate : int
            Desired sampling rate for input data; sampling rate that detect()
            and locate() will be computed at.

        """

        super().__init__(sampling_rate)

        # Onset position override
        self.onset_centred = True
