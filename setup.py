"""
Wyrm - a python project splicing python machine learning seismology tools into the Earthworm Message Transport System

Wyrm is a open-source project that builds on the PyEarthworm, ObsPy, Numpy, and SeisBench APIs to facilitate
testing and operationalization of Python-based machine learning workflows that use Earthworm messages as inputs
and outputs

:copyright: Nathan T. Stevens and Pacific Northwest Seismic Network (pnsn.org)
:license: AGPL-3.0
"""
from setuptools import setup, find_packages

setup(
    name='wyrm',
    verions="0.0.0",
    description='A package joining Python ML workflows to the Earthworm Message Transport System for streaming waveform data operations',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'cython',
        'obspy',
        'pandas',
        'seisbench'
    ]
)