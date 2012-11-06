"""
Defines models for power systems components, including 
:class:`~powersystems.PowerSystem`, :class:`~powersystems.Bus`,
:class:`~powersystems.Load` and  :class:`~powersystems.Line`. 
:class:`~powersystems.Generator` components can be found
in the :module:`~generators`. Each of these objects inherits an
optimization framework from :class:`~optimization.OptimizationObject`.
"""

from optimization import value,dual,OptimizationObject,OptimizationProblem
from generators import *
from commonscripts import *
import config
from config import user_config



def makeLoad(kind='varying',**kwargs):
    """
    Create a :class:`~powersystems.Load` object (if a power 
    :class:`~schedule.Schedule` is specified) or a
    cost_load_sheddingrsystems.Load_Fixed` object (if a single
    power value :attr:`P` is specified).
    """
    if 'P' in kwargs.keys(): return Load_Fixed(kind=kind, **kwargs)
    else: return Load(kind=kind,**kwargs)



class Load(OptimizationObject):
    """
    Describes a power system load (demand).
    Currently only real power is considered.
    
    :param bus: name of bus that load is on 
      (not required if ED/OPF problem)
    :param schedule: :class:`~schedule.Schedule` object
      (generally created automatically from file
      by :meth:`get_data.build_class_list`)
    :param shedding_allowed: if this load is allowed to be turned off 
    :param cost_shedding: the price of shedding 1MWh of this load
    """
    def __init__(self,kind='varying',name='',index=None,bus=None,schedule=None,
                 shedding_allowed=False,
                 cost_shedding=user_config.cost_load_shedding
                 ):
        update_attributes(self,locals()) #load in inputs
        self.init_optimization()
    def power(self,time,evaluate=False): 
        if self.shedding_allowed:
            power=self.get_variable('power',time,indexed=True)
            if evaluate: power=value(power)
            return power
        else: 
            return self.schedule.get_energy(time)
    def shed(self,time,evaluate=False): return self.schedule.get_energy(time) - self.power(time,evaluate)
    def cost(self,time): return self.cost_shedding*self.shed(time)
    def cost_first_stage(self,times): return 0
    def cost_second_stage(self,times): return sum(self.cost(time) for time in times)
    def create_variables(self,times):
        if self.shedding_allowed:
            self.add_variable('power',index=times.set,low=0)
    def create_constraints(self,times):
        if self.shedding_allowed:
            for time in times:
                self.add_constraint('max_load_power',time,self.power(time)<=self.schedule.get_energy(time))
    def create_objective(self,times):
        return sum([ self.cost(time) for time in times])

    def __str__(self): return 'd{ind}'.format(ind=self.index)    
    def __int__(self): return self.index
    def iden(self,t):     return str(self)+str(t)
    
class Load_Fixed(Load):
    """
    Describes a load that does not vary with time.
    This can be an easy way to add a load for an ED/OPF problem,
    or a system base load.
    
    :param P: real power consumed by load (MW/hr)
    """
    def __init__(self,kind='fixed',name='',index=None,bus=None,P=0,
                 shedding_allowed=False,
                 cost_load_shedding=user_config.cost_load_shedding
                 ):
        update_attributes(self,locals(),exclude=['p']) #load in inputs
        self.Pfixed = P
        self.init_optimization()
    def shed(self,time,evaluate=False): return self.Pfixed- self.power(time,evaluate)
    def power(self,time=None,evaluate=False): 
        if self.shedding_allowed:
            return self.get_variable('power',time) if evaluate else value(self.get_variable('power',time))
        else: return self.Pfixed
        
    def create_variables(self,times=None):
        if self.shedding_allowed:
            for time in times: self.add_variable('power',time=time,low=0,high=self.Pfixed)
        
class Line(OptimizationObject):
    """
    Describes a tranmission line. Currently the model
    only considers real power flow under normal conditions.
    
    :param From: name of bus line originates at
    :param To:   name of bus line connects to
    :param X:    line reactance (p.u.)
    :param Pmax: maximum (positive direction) power flow over line
    :param Pmin: maximum (negative direction) power flow over line.
      Defaults to -:attr:`Pmax` if not specified.
    """
    def __init__(self,name='',index=None,From=None,To=None,X=0.05,Pmax=9999,Pmin=None,**kwargs):
        update_attributes(self,locals()) #load in inputs
        if self.Pmin is None: self.Pmin=-1*self.Pmax #reset default to be -Pmax
        self.init_optimization()
    def power(self,time): return self.get_variable('power',time,indexed=True)
    def price(self,time):
        '''congestion price on line'''
        return dual(self.get_constraint('line flow',time))
    def create_variables(self,times):
        self.add_variable('power',index=times.set)
    def create_constraints(self,times,buses):
        '''create the constraints for a line over all times'''
        busNames=getattrL(buses,'name')
        iFrom,iTo=busNames.index(self.From),busNames.index(self.To)
        for t in times:
            line_flow_ij=self.power(t) == (1/self.X) * (buses[iFrom].angle(t) - buses[iTo].angle(t))
            self.add_constraint('line flow',t,line_flow_ij)
            self.add_constraint('line limit high',t,self.power(t)<=self.Pmax)
            self.add_constraint('line limit low',t,self.Pmin<=self.power(t))
        return 
    def __str__(self): return 'k{ind}'.format(ind=self.index)
    def __int__(self): return self.index
    def iden(self,t): return str(self)+str(t)


class Bus(OptimizationObject):
    """
    Describes a bus (usually a substation where one or more
    tranmission lines start/end).
    
    :param isSwing: flag if the bus is the swing bus 
      (sets the reference angle for the system)
    """
    def __init__(self,name=None,index=None,isSwing=False):
        update_attributes(self,locals()) #load in inputs
        self.generators,self.loads=[],[]
        self.init_optimization()
    
    def angle(self,time): return self.get_variable('angle',time,indexed=True)
    def price(self,time): return dual(self.get_constraint('power balance',time))
    def Pgen(self,t,evaluate=False):
        if evaluate: return sum(value(gen.power(t)) for gen in self.generators)
        else: return sum(gen.power(t) for gen in self.generators)
    def Pload(self,t,evaluate=False):  
        if evaluate: return sum(value(ld.power(t)) for ld in self.loads)
        else: return sum(ld.power(t) for ld in self.loads)
    def power_balance(self,t,Bmatrix,allBuses):
        if len(allBuses)==1: lineFlowsFromBus=0
        else: lineFlowsFromBus=sum([Bmatrix[self.index][otherBus.index]*otherBus.angle(t) for otherBus in allBuses]) #P_{ij}=sum_{i} B_{ij}*theta_j ???
        return sum([ -lineFlowsFromBus,-self.Pload(t),self.Pgen(t) ])
    def create_variables(self,times):
        self.add_children(self.generators,'generators')
        self.add_children(self.loads,'loads')
        logging.debug('added bus {} components - generators and loads {}'.format(self.name,show_clock()))
#        if len(self.generators)<50:
        for gen in self.generators: gen.create_variables(times)             
#        else:
#            for gen in self.generators:
#                threading.Thread(target=_call_generator_create_variables,args=(gen,times)).start()
#            else:
#                for th in threading.enumerate():  
#                    if th is threading.current_thread(): continue
#                    else: th.join()

        logging.debug('created generator variables {}'.format(show_clock()))
        for load in self.loads: load.create_variables(times)
        logging.debug('created load variables {}'.format(show_clock()))
        self.add_variable('angle',index=times.set)
        logging.debug('created bus variables ... returning {}'.format(show_clock()))
        return
    def create_objective(self,times): return self.cost_first_stage(times) + self.cost_second_stage(times)
    def cost_first_stage(self,times):
        return sum(gen.cost_first_stage(times) for gen in self.generators) + \
            sum(load.cost_first_stage(times) for load in self.loads)
    def cost_second_stage(self,times):
        return sum(gen.cost_second_stage(times) for gen in self.generators) + \
            sum(load.cost_second_stage(times) for load in self.loads)            
    def create_constraints(self,times,Bmatrix,buses):
        for gen in self.generators: gen.create_constraints(times)
        for load in self.loads: load.create_constraints(times)
        nBus=len(buses)
        for time in times:
            self.add_constraint('power balance',time, self.power_balance(time,Bmatrix,buses)==0) #power balance must be zero
            if nBus>1 and self.isSwing: 
                self.add_constraint('swing bus',time, self.angle(time)==0)#swing bus has angle=0
        return
    # def clear_constraints(self):
    #     self.constraints={}
    #     for gen in self.generators: gen.clear_constraints()
    #     for load in self.loads: load.clear_constraints()

    def iden(self,t):   return str(self)+str(t)
    def __str__(self):  return 'i{ind}'.format(ind=self.index)
    
class PowerSystem(OptimizationProblem):
    '''
    Power systems object which is the container for all other components.
    
    :param generators: list of :class:`~powersystem.Generator` objects
    :param loads: list of :class:`~powersystem.Load` objects
    :param lines: list of :class:`~powersystem.Line` objects
    
    Other settings are inherited from `user_config`.
    '''
    def __init__(self, generators, loads, lines=None):
        update_attributes(self,locals(),exclude=['generators','loads','lines']) #load in inputs
        self.num_breakpoints           = user_config.breakpoints
        self.load_shedding_allowed     = user_config.load_shedding_allowed
        self.cost_load_shedding        = user_config.cost_load_shedding
        self.dispatch_decommit_allowed = user_config.dispatch_decommit_allowed
        self.reserve_fixed             = user_config.reserve_fixed
        self.reserve_load_fraction     = user_config.reserve_load_fraction

        
        if lines is None: lines=[]    
            
        buses=self.make_buses_list(loads,generators)
        self.create_admittance_matrix(buses,lines)
        self.init_optimization()
        
        self.add_children(buses,'buses')
        self.add_children(lines,'lines')
        
        #add system mode parameters to relevant components
        self.set_load_shedding(self.load_shedding_allowed) #set load shedding
        for load in loads:
                try: load.cost_breakpoints = self.num_breakpoints
                except AttributeError: pass #load has no cost model   
        for gen in generators:
            gen.dispatch_decommit_allowed = self.dispatch_decommit_allowed
            try: gen.cost_breakpoints = self.num_breakpoints
            except AttributeError: pass #gen has no cost model
            
    def set_load_shedding(self,is_allowed):
        '''set system mode for load shedding'''
        for load in self.loads():
            load.shedding_allowed=is_allowed 
            load.cost_shedding=self.cost_load_shedding
             
    def make_buses_list(self,loads,generators):
        """
        Create list of :class:`powersystems.Bus` objects 
        from the load and generator bus names. Otherwise
        (as in ED,UC) create just one (system)
        :class:`powersystems.Bus` instance.
        
        :param loads: a list of :class:`powersystems.Load` objects
        :param generators: a list of :class:`powersystems.Generator` objects
        :returns: a list of :class:`powersystems.Bus` objects
        """
        busNameL=[]
        busNameL.extend(getattrL(generators,'bus'))
        busNameL.extend(getattrL(loads,'bus'))
        busNameL=unique(busNameL)
        buses=[]
        swingHasBeenSet=False
        for b,busNm in enumerate(busNameL):
            newBus=Bus(name=busNm,index=b)
            for gen in generators: 
                if gen.bus==newBus.name: newBus.generators.append(gen) 
                if not swingHasBeenSet: newBus.isSwing=swingHasBeenSet=True
            for ld in loads: 
                if ld.bus==newBus.name: newBus.loads.append(ld)             
            buses.append(newBus)
        return buses
    def create_admittance_matrix(self,buses,lines):
        """
        Creates the admittance matrix (B), 
        with elements = total admittance of line from bus i to j.
        Used in calculating the power balance for OPF problems.
        
        :param buses: list of :class:`~powersystems.Line` objects
        :param lines: list of :class:`~powersystems.Bus` objects
        """
        nB=len(buses)
        self.Bmatrix=np.zeros((nB,nB))
        namesL=[bus.name for bus in buses]
        for line in lines:
            busFrom=buses[namesL.index(line.From)]
            busTo=buses[namesL.index(line.To)]
            self.Bmatrix[busFrom.index,busTo.index]+=-1/line.X
            self.Bmatrix[busTo.index,busFrom.index]+=-1/line.X
        for i in range(0,nB): 
            self.Bmatrix[i,i]=-1*sum(self.Bmatrix[i,:])
    def loads(self): return flatten(bus.loads for bus in self.buses)
    def generators(self): return flatten(bus.generators for bus in self.buses)
    def create_variables(self,times):
        self.add_variable('cost_first_stage')
        self.add_variable('cost_second_stage')        
        self.add_set('times',[str(t) for t in times])
        times.set=self._model.times
        for bus in self.buses:  bus.create_variables(times)
        for line in self.lines: line.create_variables(times)
        logging.debug('... created power system vars... returning... {}'.format(show_clock()))
        #for var in self.all_variables(times).values(): self.add_variable(var)
    def cost_first_stage(self,scenario=None): return self.get_component('cost_first_stage',scenario=scenario)    
    def cost_second_stage(self,scenario=None): return self.get_component('cost_second_stage',scenario=scenario)
    def create_objective(self,times): 
        self.add_objective(self.cost_first_stage()+self.cost_second_stage())
    def create_constraints(self,times):
        for bus in self.buses: bus.create_constraints(times,self.Bmatrix,self.buses)
        for line in self.lines: line.create_constraints(times,self.buses)

        # system reserve constraint
        if (self.reserve_fixed>0 or self.reserve_load_fraction>0):
            for time in times:
                required_generation_availability = self.reserve_fixed + (1.0 + self.reserve_load_fraction) * sum(load.power(time) for load in self.loads())
                generation_availability = sum(gen.power_available(time) for gen in self.generators())
                self.add_constraint('reserve', generation_availability >= required_generation_availability, time=time )
        
        self.add_constraint('system_cost_first_stage',self.cost_first_stage()==sum(bus.cost_first_stage(times) for bus in self.buses))
        self.add_constraint('system_cost_second_stage',self.cost_second_stage()==sum(bus.cost_second_stage(times) for bus in self.buses))
    def iden(self,time=None): 
        name='system'
        if time is not None: name+='_'+str(time)
        return name

    def get_generators_without_scenarios(self):
        return filter(lambda gen: getattr(gen,'has_scenarios',False)==False, self.generators())

            
    def get_generator_with_scenarios(self):
        gens = filter(lambda gen: getattr(gen,'has_scenarios',False), self.generators())
        if len(gens)>1: raise NotImplementedError('Dont handle the case of multiple stochastic generators')
        elif len(gens)==0: return []
        else: return gens[0]
    def get_generator_with_observed(self):
        return filter(lambda gen: getattr(gen,'observed_values',None) is not None, self.generators())[0]

    def get_finalconditions(self, stage_solution):
        times = stage_solution.times
        tEnd = times.non_overlap_times.last()
        for gen in self.generators():
            if stage_solution.is_stochastic:
                finalstatus = dict(
                    P =  stage_solution.observed_generator_power[gen][tEnd.Start], 
                    u =  stage_solution.stage_generators_status[gen][tEnd.Start], 
                    hoursinstatus = gen.gethrsinstatus(
                        tEnd, 
                        times, 
                        status_var = lambda time: stage_solution.stage_generators_status[gen][time.Start]
                        )
                    )
            else: finalstatus = gen.getstatus(t=tEnd,times=times)
            gen.finalstatus = finalstatus
        return
        
    def set_initialconditions(self, initTime, stage_number, stage_solutions):
        #first stage of problem already has initial time defined
        if stage_number == 0: return
        for gen in self.generators():
            finalstatus = getattr(gen, 'finalstatus', {})
            if finalstatus: 
                gen.set_initial_condition(time=initTime, **finalstatus)
                del gen.finalstatus
        return 
