import pytest
from obspy import read
from obspy.core.trace import Stats
from obspy.core.util import AttribDict
from obspy.core.tests.test_stats import TestStats
from obspy.core.tests.test_util_attribdict import TestAttribDict
from pandas import Series
from PULSE.util.header import MLStats

class TestMLStats(TestStats):

    egstats = read()[0].stats

    def test_init(self):
        header = MLStats()
        # Assert inheritance
        assert isinstance(header, Stats)
        assert isinstance(header, AttribDict)
        # Assert defaults
        assert header.location == ''
        assert header.processing == []
        assert header.model == ''
        assert header.weight == ''
        # Test dict input
        header = MLStats({'station': 'GPW', 'network': 'UW',
                          'location':'', 'channel': 'EHZ',
                          'model':'EQTransformer','weight':'pnw'})
        assert header.network == 'UW'
        assert header.station == 'GPW'
        assert header.location == ''
        assert header.channel == 'EHZ'
        assert header.model == 'EQTransformer'
        assert header.weight == 'pnw'
        # Test Stats input
        header = MLStats(self.egstats)
        for _k, _v in self.egstats.items():
            assert header[_k] == _v
        # Test Stats input
        tr = read()[0]
        header = MLStats(tr.stats)
        for _k, _v in tr.stats.items():
            if _k == 'location' and _v == '':
                assert header[_k] == ''
            else:
                assert header[_k] == _v
        
        # Other types inputs raises
        with pytest.raises(TypeError):
            header = MLStats('abc')
            header = MLStats(['abc'])

    def test_str(self):
        header = MLStats()
        assert isinstance(header.__str__(), str)

    def test_utc2nearest_index(self):
        header = MLStats(self.egstats)
        t0 = self.egstats.starttime
        dt = self.egstats.delta
        eta = dt*0.1
        # Test starttime equivalent
        assert 0 == header.utc2nearest_index(t0)
        # Test small offset
        assert 0 == header.utc2nearest_index(t0 + eta)
        # Test exact delta offset
        assert 1 == header.utc2nearest_index(t0 + dt)
        # Test nearby delta offset
        assert 1 == header.utc2nearest_index(t0 + dt + eta)
        assert 1 == header.utc2nearest_index(t0 + dt - eta)
        # Test negative
        assert -1 == header.utc2nearest_index(t0 - dt)
        assert -1 == header.utc2nearest_index(t0 - dt + eta)
        assert -1 == header.utc2nearest_index(t0 - dt - eta)

    def test_copy(self):
        header = MLStats(self.egstats)
        header2 = header.copy()
        header2.station='YEAH'
        assert header != header2
        assert header2.station == 'YEAH'
        assert header.station == 'RJOB'

    def test_properties(self):
        header = MLStats(self.egstats)
        # Test all default values (base values) occur
        for _attr in self.egstats.defaults.keys():
            assert self.egstats[_attr] == header[_attr]
            assert self.egstats[_attr] == getattr(header, _attr)
        # Assert that compund values are present
        for _attr in ['inst','site','comp','mod','nslc','sncl']:
            assert hasattr(header, _attr)
        # Assert that nslc for empty mod/weight matches ID
        assert header.id == header.nslc
        # Assert that nslc does not match if mod or weight are assigned
        header.model='EQTransformer'
        assert header.id == f'{header.nslc}.{header.model}.'
        header.weight='pnw'
        assert header.id == f'{header.nslc}.{header.model}.{header.weight}'
        header.model=''
        assert header.id == f'{header.nslc}..{header.weight}'
        # Test compound codes
        header.model='EQTransformer'
        assert header.comp == header.channel[-1]
        assert header.inst == header.nslc[:-1]
        assert header.site == f'{header.network}.{header.station}.{header.location}'
        assert header.mod == f'{header.model}.{header.weight}'

    def test_get_id_keys(self):
        header = MLStats(self.egstats)
        assert isinstance(header.get_id_keys(), AttribDict)


        

