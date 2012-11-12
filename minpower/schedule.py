"""
Time and schedule related models.
"""

import dateutil
from datetime import timedelta, datetime
from commonscripts import *
from operator import attrgetter

def get_schedule(filename):
    return ts_from_csv(filename)

def make_times_basic(N):
    '''make a :class:`schedule.TimeIndex` of N times with hourly interval'''
    return TimeIndex(date_range('00:00:00', periods=N, freq='H'))
    
def just_one_time():
    '''make a TimeIndex with just one time in it'''
    return make_times_basic(1)

class TimeIndex(object):
    '''a list of times (underlying model is pandas.Index)'''
    def __init__(self, index):
        strings = ['t%02d'%i for i in range(len(index))]
        self.times = index.copy()
        self.strings = Series(strings,index=self.times)
        self._set = self.strings.values.tolist()
        
        self.get_interval()
        self.Start = self.times[0]
        self.startdate = self.Start.date()
        
        self.End = self.times[-1] + self.interval
        self.span = self.End-self.Start
        self.spanhrs = hours(self.span)
        
        self.set_initial()
                
        self._subdivided = False
        self._int_overlap = 0
        self._index_based = True
        self._start_index = 0

    def set_initial(self,initialTime=None): 
        if initialTime: self.initialTime= initialTime
        else: 
            self.initialTime = pd.Timestamp(self.Start - self.interval)
            self.initialTime.index = 'Init'
        
    def get_interval(self):
        freq = self.strings.index.freq
        if freq is not None:
            self.interval = freq
            if self.interval.freqstr=='H':
                self.intervalhrs = self.interval.n
            else:
                self.intervalhrs = None # TODO
        else:            
            self.interval = self.times[1] - self.times[0]
            self.intervalhrs = self.interval.total_seconds() / 3600.0
        return

    def __contains__(self, item): return item in self.times
    def __repr__(self): return repr(self.times)
    def __len__(self): return len(self.times)
    def __getitem__(self, i, circular=False): 
        if i==-1 and not circular:
            return self.initialTime
        else:
            return self.strings[i]
    def last(self): return self.__getitem__(-1, circular=True)
    
    def __getslice__(self, i, j): return self.strings[i:j]

    def non_overlap(self):
        if self._subdivided and self._int_overlap > 0:
            return TimeIndex(self.times.ix[:-1-int_overlap+1])
        else: 
            return self
        return 

    def subdivide(self, division_hrs=24, overlap_hrs=0):
        int_division = int(division_hrs / self.intervalhrs)
        int_overlap = int(overlap_hrs / self.intervalhrs)
        subsets = []
        for stg in range(int(len(self) / int_division)):
            start = stg * int_division
            end_point = start + int_division + int_overlap
            end_point = min(end_point, len(self))

            subset = TimeIndex(self.times[start:end_point])
            subset.strings = self.strings[start:end_point]
            subset._set = subset.strings.values.tolist()
            subset._int_overlap = int_overlap
            subsets.append(subset)

        return subsets
        
def is_init(time):
    return getattr(time,'index',None)=='Init'