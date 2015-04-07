'''
Basic implementation of contract

Author: Antonio Iannopollo
'''

from pyco.parser.parser import LTL_PARSER
from pyco.parser.lexer import BaseSymbolSet
from pyco.attribute import Attribute
from pyco.formula import Literal, Conjunction, Disjunction, Negation
from pyco.observer import Observer
from copy import deepcopy
from pyco.ltl3ba import (Ltl3baRefinementStrategy, Ltl3baCompatibilityStrategy,
                         Ltl3baConsistencyStrategy)
import logging

LOG = logging.getLogger()

LOG.debug('in contract.py')

class Port(Observer):
    '''
    This class implements a port for a contract. It contains a literal but it
    keeps constant its base name
    '''

    def __init__(self, base_name, contract=None, literal=None, context=None):
        '''
        Creates a new port and associates a literal.
        If no literal is provided, a new one will be created.

        :param base_name: base name of the port
        :type base_name: string
        :param literal: literal to be associated with the port. If None, a
            new Literal will be created
        :type literal: LTLFormula.Literal
        :param context: a context object to define the scope of literal unique
            naming
        :type context: object
        '''


        self.base_name = base_name
        self.context = context

        self._contract = None
        #it's  property
        self.contract = contract

        if literal is None:
            literal = Literal(base_name, context)

        self.literal = literal
        self.literal.attach(self)


    def update(self, updated_subject):
        '''
        Implementation of the update method from a attribute according to
        the observer pattern
        '''

        updated_literal = updated_subject.get_state()

        #if updated_name not in self.port_names:
        #    raise KeyError('attribute not in literals dict for the formula')

        #attach to the new literal
        updated_literal.attach(self)

        #detach from the current literal
        self.literal.detach(self)

        #update the literals
        self.literal = updated_literal

    def merge(self, port):
        '''
        Merges the current port literal with another port or literal
        '''
        self.literal.merge(port.literal)

        return self

    def is_connected_to(self, port):
        '''
        Returns true if self references the same literal than port
        '''
        if self.unique_name == port.unique_name:
            return True
        else:
            return False

    @property
    def contract(self):
        '''
        contract using the port
        '''
        return self._contract

    @contract.setter
    def contract(self, value):
        '''
        fails if assign multiple times
        '''
        if self._contract is not None:
            raise PortDeclarationError('assigning port to contract multiple times')

        #check the contract has this port
        if value is not None and self not in value.ports_dict.viewvalues():
            raise PortDeclarationError('contract does not contain this port')

        self._contract = value

    @property
    def unique_name(self):
        '''
        return unique_name associated to self.literal
        '''
        return self.literal.unique_name

    @property
    def is_input(self):
        '''
        Returns true if the port is a input of the connected contract
        '''

        if self.contract is None:
            raise PortDeclarationError('port is not used by any contract')
        else:
            if self.base_name in self.contract.input_ports_dict:
                return True
            else:
                return False

    @property
    def is_output(self):
        '''
        Returns True if the port is an output
        '''
        return not self.is_input




class Contract(object):
    '''
    This class implements the basic concept of contract. This object is able
    to process input formulas (one for the assumptions, and one for the
    guarantees). The biggest difference with respect to the theoretical entity
    of a contract is that here we require also the list of input and output
    ports to be provided.
    This implementation supports the basic operation on contracts, such as
    refinement check, composition, compatibility and consistency checks.
    No requirement of GR1 formulas needed.
    '''

    def __init__(self, base_name, input_ports, output_ports, assume_formula,
                 guarantee_formula, symbol_set_cls=BaseSymbolSet, context=None,
                 saturated=True):
        '''
        Instantiate a contract.

        :param base_name: a name for the contract. If the name is not unique,
            a unique name will be provided as an Attribute
        :type base_name: string
        :param input_ports: set of input ports associated with the contract
        :type input_ports: set or list  of strings, each of them being an
            environment-controlled literal, or a list of pairs (name, Literal)
        :param output_ports: set of output ports associated with the contract
        :type output_ports: set or list of string , each of them being a
            contract-controlled literal, or a list of pairs (name, Literal)
        :param assume_formula: assume part of the contract specification
        :type assume_formula: string or LTLFormula object
        :param guarantee_formula: guarantee part of the contract specification
        :type guarantee_formula: string or LTLFormula object
        :param symbol_set_cls: symbol set class, used to decode furmula strings
            and to generate string representation of LTLFormula objects
        :type symbol_set_cls: class, preferably extending
            pyco.parser.lexer.BaseSymbolSet
        :param context: fomrula context for unique variable naming
        :type context: object
        '''

        self.symbol_set_cls = symbol_set_cls
        self.context = context

        #define attribute name for the contract
        self.name_attribute = Attribute(base_name, self.context)

        #first, we need to retrieve formulas and literals from formulas
        #possibilities are that formulae will be either string or LTLFormula
        #object
        #Let's assume they are string, then LTLFormula objects
        #Also, in case they are strings, we need to insure that the same
        #literal in either formula is associated to the same attribute.
        #This means the context of both formulae is the current Contract obj
        try:
            self.assume_formula = LTL_PARSER.parse(assume_formula, \
                    context=self.context, symbol_set_cls=symbol_set_cls)
        except TypeError:
            #the formula is not a string, we assume is a LTLFormula object
            self.assume_formula = assume_formula

        try:
            self.guarantee_formula = LTL_PARSER.parse(guarantee_formula, \
                    context=self.context, symbol_set_cls=symbol_set_cls)
        except TypeError:
            self.guarantee_formula = guarantee_formula

        #put it in saturated form
        if not saturated:
            not_assumpt = Negation(self.assume_formula)
            self.guarantee_formula = \
                    Disjunction(not_assumpt, self.guarantee_formula)


        #the contract has to mantain a detailed list of ports.
        #It means that it needs to be an observer of literals in formulae
        #and it needs to create new attributes for ports which are not mentioned
        #in formulae

        #start assuming the input and output lists are including literals
        try:
            self.input_ports_dict = \
                    {key: value for (key, value) in input_ports.items()}
        #in case input_ports is a list of string, we'll try to match
        #literals in the formula
        except AttributeError:
            input_ports = set(input_ports)
            self.input_ports_dict = {key : None for key in input_ports}
        else:
            #register this contract as the port owner
            for port in self.input_ports_dict.viewvalues():
                port.contract = self
        #and outputs
        try:
            self.output_ports_dict = \
                    {key: value for (key, value) in output_ports.items()}
        #in case input_ports is a list of string, we'll try to match
        #literals in the formula
        except AttributeError:
            output_ports = set(output_ports)
            self.output_ports_dict = {key : None for key in output_ports}
        else:
            #register this contract as the port owner
            for port in self.output_ports_dict.viewvalues():
                port.contract = self

        #try process input and outport ports
        #if a port is associated with None, a literal will be searched
        #in formulae, otherwise a new Port is created
        for literal_name in self.ports_dict.viewkeys():
            #port lookup looks for the correct dictionary
            port_dict = self.port_lookup(literal_name)

            if port_dict[literal_name] is None:
                #try to associate by base_name
                if literal_name in self.formulae_dict:
                    port_dict[literal_name] = \
                        Port(literal_name, contract=self, literal=\
                        self.formulae_dict[literal_name], \
                        context=self.context)
                #otherwise create new Port
                else:
                    port_dict[literal_name] = \
                        Port(literal_name, contract=self, context=self.context)

            ##observer pattern - attach to the subject
            #port_dict[literal_name].attach(self)

        #check if there is something wrong

        #we need to make sure there are not ports which are both input and
        #output
        if not set(self.input_ports_dict.viewkeys()).isdisjoint( \
                set(self.output_ports_dict.viewkeys())):
            raise PortDeclarationError(self.input_ports_dict.viewkeys() & \
                    self.output_ports_dict.viewkeys())


        #now we need to check that the declared input and output ports
        #match the formulae.
        #It is possible, however, that some ports are not mentioned at all
        #in the formulae (meaning no costraints on values), or that both
        #input and output ports are mentioned as literal in either assume
        #or guarantee formulae.
        #What we can do, is making sure that there are not literals in
        #assumptions and guarantees which do not match ports


        #sometimes some literals in formulae do not have a match
        #we can try to match them with known ports based on their base_name
        for key in self.formulae_reverse_dict.viewkeys() - \
                self.reverse_ports_dict.viewkeys():

            literal = self.formulae_reverse_dict[key]
            try:
                literal.merge(self.ports_dict[literal.base_name].literal)
            except KeyError:
                raise PortMappingError(key)


        #Initialize a dict in which there is a reference to all the contracts
        #used to obtain this contract through composition.
        #The dict is inializated as empty
        self.origin_contracts = {}


    def copy(self):
        '''
        create a copy, with new disconnected ports, of the current contract
        '''

        new_contract = deepcopy(self)
        new_contract.assume_formula.reinitialize()
        new_contract.guarantee_formula.reinitialize()
        new_contract.name_attribute = \
                Attribute(self.name_attribute.base_name, self.context)

        return new_contract


    def compose(self, other_contract, new_name=None, composition_mapping=None):
        '''
        Compose the current contract with the one passed as a parameter.
        The operations to be done are: merge the literals, and merge the
        formulae.
        Given a contract C = (A, G) and a contract C1 = (A1, G1), the
        composition of the two will be a contract
        C2 = ((A & A1) | !(G & G1) , G & G1)

        :param other_contract: contract to be used for composition
        :type other_contract: Contract
        :param connection_list: optional list of pairs of base_names specifying
            the ports to be connected
        :type connection_list: list of tuples (pairs)
        '''

        if composition_mapping is None:
            composition_mapping = CompositionMapping(self, other_contract, self.context)
        if new_name is None:
            new_name = '%s-x-%s' % (self.name_attribute.base_name, \
                    other_contract.name_attribute.base_name)

        #in case of composition, we need to infer the composition contract
        #ports
        #we populate the new port list with all the ports from the composed
        #contracts, naming them merging the source contract and the port
        new_inputs = {'%s_%s' % \
            (self.name_attribute.unique_name, base_name): Port('%s_%s' % \
            (self.name_attribute.unique_name, base_name), literal=port.literal, context=self.context) \
            for (base_name, port) in self.input_ports_dict.items()}
        #update with the other_contract ports
        new_inputs.update({'%s_%s' % \
            (other_contract.name_attribute.unique_name, base_name): Port('%s_%s' % \
            (self.name_attribute.unique_name, base_name), literal=port.literal, context=self.context) \
            for (base_name, port) in other_contract.input_ports_dict.items()})

        #and outputs
        new_outputs = {'%s_%s' % \
            (self.name_attribute.unique_name, base_name): Port('%s_%s' % \
            (self.name_attribute.unique_name, base_name), literal=port.literal, context=self.context) \
            for (base_name, port) in self.output_ports_dict.items()}
        #update with the other_contract ports
        new_outputs.update({'%s_%s' % \
            (other_contract.name_attribute.unique_name, base_name): Port('%s_%s' % \
            (self.name_attribute.unique_name, base_name), literal=port.literal, context=self.context) \
            for (base_name, port) in other_contract.output_ports_dict.items()})


        for (port, other_port) in connection_list:
            self.connect_to_port(port, other_port)
            #process ports
            #input/input, we need to remove one input in the new contract
            port_name = port.base_name
            other_port_name = other_port.base_name
            if (port_name in self.input_ports_dict) and \
                    (other_port_name in other_contract.input_ports_dict):
                del new_inputs['%s_%s' % \
                    (other_contract.name_attribute.unique_name, \
                        other_port_name)]
            #input/output becomes a output
            elif (port_name in self.input_ports_dict) and \
                    (other_port_name in other_contract.output_ports_dict):
                del new_inputs['%s_%s' % \
                    (self.name_attribute.unique_name, port_name)]
            #output/input
            elif (port_name in self.output_ports_dict) and \
                    (other_port_name in other_contract.input_ports_dict):
                del new_inputs['%s_%s' % \
                    (other_contract.name_attribute.unique_name, \
                        other_port_name)]
            #output/output
            #if ((port_name in self.output_ports_dict) and \
            #        (other_port_name in other_contract.output_ports_dict)):
            else:
                raise PortConnectionError('Cannot connect two output ports')


        and_of_assumptions = Conjunction(self.assume_formula, \
                other_contract.assume_formula, merge_literals=False)

        new_guarantees = Conjunction(self.guarantee_formula, \
                other_contract.guarantee_formula, merge_literals=False)

        neg_guarantees = Negation(new_guarantees)

        new_assumptions = Disjunction(and_of_assumptions, neg_guarantees, \
                merge_literals=False)

        new_contract = Contract(new_name, new_inputs, new_outputs, new_assumptions,
                                new_guarantees, self.symbol_set_cls, self.context)

        #add the two contracts as source contracts
        new_contract.origin_contracts[self.name_attribute.unique_name] = self
        new_contract.origin_contracts[other_contract.name_attribute.unique_name] = other_contract


        return new_contract

    def connect_to_port(self, port_ref, other_port_ref):
        '''
        Connect a port of the current contract with a port of another contract.
        Here it is allowed connecting two output ports.

        :param port_name: base name of the current contract port
        :type port_name: string
        :param other_contract: contract to be connected to
        :type other_contract: Contract object
        :param other_port_name: name of the port to be connected to
        :type other_port_name: string
        '''
        #merge only if the contract is the rightful owner of the port
        if port_ref.contract is self:
            port_ref.merge(other_port_ref)
        else:
            raise PortDeclarationError()

    def is_refinement(self, abstract_contract, strategy_obj=None):
        '''
        Checks whether the calling contract refines abstract_contract

        :returns: boolean
        '''

        #If a strategy is not defined, uses Ltl3ba
        if strategy_obj is None:
            strategy_obj = Ltl3baRefinementStrategy(self, delete_files=False)

        return strategy_obj.check_refinement(abstract_contract)

    def is_consistent(self, strategy_obj=None):
        '''
        Returns True if the contract is consistent. False otherwise.
        A contract is consistent iff it is not self-contradicting. In case of a
        self-contradicting contract, it is impossible to find an implementation
        that satisfies it. Thus to verify consistency, we need to check that the
        guarantee formula is not an empty formula
        '''
        if strategy_obj is None:
            strategy_obj = Ltl3baConsistencyStrategy(self, delete_files=False)

        return strategy_obj.check_consistency()

    def is_compatible(self, strategy_obj=None):
        '''
        Returns True if the contract is compatible, False otherwise.
        A contract is compatible iff there is at least a valid environment in
        which it can operate. Therefore we need to verify that the assumption
        formula is not empty.
        '''

        if strategy_obj is None:
            strategy_obj = Ltl3baCompatibilityStrategy(self, delete_files=False)

        return strategy_obj.check_compatibility()

    def __str__(self):
        '''
        Defining print representation for a contract
        '''
        description = []
        description.append('Contract %s ( %s )\n' % \
            (self.name_attribute.unique_name, self.name_attribute.base_name))

        description.append('\tInput ports:\n')

        for base_name, port in self.input_ports_dict.items():

            description.append('\t\t%s ( %s )\n' % \
                    (port.unique_name, base_name))

        description.append('\tOutput ports:\n')

        for base_name, port in self.output_ports_dict.items():
            description.append('\t\t%s ( %s )\n' % \
                    (port.unique_name, base_name))

        description.append('\tAssumption\n')
        description.append('\t\t%s\n' % \
                self.assume_formula.generate(self.symbol_set_cls))

        description.append('\tGuarantee\n')
        description.append('\t\t%s\n' % \
                self.guarantee_formula.generate(self.symbol_set_cls))

        return ''.join(description)


    def port_lookup(self, literal_name):
        '''
        Given a literal name, returns the dictionary (either input or output)
        in which it is defined
        '''

        if literal_name in self.input_ports_dict.viewkeys():
            port_dict = self.input_ports_dict
        elif literal_name in self.output_ports_dict.viewkeys():
            port_dict = self.output_ports_dict
        else:
            raise KeyError('port not defined for literal %s' % literal_name)

        return port_dict


    def __getattr__(self, port_name):
        '''
        Checks if port_name is in ports_dict and consider it as a Contract attribute.
        IF it is present, returns the
        requested port, otherwise raises a AttributeError exception
        '''

        if port_name in self.ports_dict:
            return self.ports_dict[port_name]
        else:
            raise AttributeError


    @property
    def port_names(self):
        '''
        Returns an updated set of port names
        '''
        return self.input_ports_dict.viewkeys() | \
                self.output_ports_dict.viewkeys()


    @property
    def ports_dict(self):
        '''
        Return an update dict of all the contract ports
        '''
        return dict( self.input_ports_dict.items() + \
                        self.output_ports_dict.items() )

    @property
    def reverse_ports_dict(self):
        '''
        Returns a dict which has uniques names as keys, and ports as values
        '''
        return dict( self.reverse_input_ports_dict.items() + \
                        self.reverse_output_ports_dict.items())

    @property
    def reverse_input_ports_dict(self):
        '''
        Returns a dict which has uniques names as keys, and ports as values
        '''
        return {key: value for (key, value) in zip( \
                [port.unique_name \
                    for port in self.input_ports_dict.viewvalues()], \
                self.input_ports_dict.viewvalues() )}

    @property
    def reverse_output_ports_dict(self):
        '''
        Returns a dict which has uniques names as keys, and ports as values
        '''
        return {key: value for (key, value) in zip( \
                [port.unique_name \
                    for port in self.output_ports_dict.viewvalues()], \
                self.output_ports_dict.viewvalues() )}


    @property
    def formulae_dict(self):
        '''
        return a dict of literals used in contract formulae, indexed by
        base_name
        '''
        return dict(self.assume_formula.get_literal_items() | \
                    self.guarantee_formula.get_literal_items() )

    @property
    def formulae_reverse_dict(self):
        '''
        return a dict of lterals used in contract formulae, indexed by
        unique_name
        '''
        #use the formulae instead of the dict because the dicts
        #overrides duplicates

        try:
            _, values = zip(* (self.assume_formula.get_literal_items() | \
                            self.guarantee_formula.get_literal_items()))
        except ValueError:
            LOG.debug('no literals??')
            return {}
        else:
            return {key: value for (key, value) in zip( \
                [literal.unique_name for literal in values], \
                    values)}

    def non_composite_origin_set(self):
        '''
        Return the set of noncomposite origin contracts
        '''
        if self.origin_contracts == {}:
            raise NonCompositeContractError()

        origin_set = set()
        look_list = self.origin_contracts.values()

        for contract in look_list:
            try:
                #access the composite list of c.
                #if c has no origin contracts, is what we are looking for.
                #otherwise expand look_list
                look_list += contract.origin_contracts.values()
            except NonCompositeContractError:
                origin_set.add(contract)

        return origin_set

    @property
    def base_name(self):
        '''
        Returns contract base_name
        '''
        return self.name_attribute.base_name

    @property
    def unique_name(self):
        '''
        Returns contract unnique name
        '''
        return self.name_attribute.unique_name



#class PortMapping(object):
#    '''
#    Encapsulate the information needed to remap a set of ports
#    to another
#    '''
#
#    def __init__(self):
#        '''
#        init operations
#        '''
#        self.mapping = set()
#
#    def add(self, port, other_port):
#        '''
#        basic method to add constraints
#        '''
#        self.mapping.add((port, other_port))


class CompositionMapping(object):
    '''
    Collects the information abou port mapping during a contract composition.
    During composition, it may happen that two original contracts have ports
    with the same name.
    This class helps defining explicit relations between ports before and after
    composition
    '''

    def __init__(self, contract, other_contract, context=None):
        '''
        Init port mapping
        '''
        self.mapping = {}
        self.context = context
        self.contract = contract
        self.other_contract = other_contract

    def _validate_port(self, port):
        '''
        raises an exception if port is not related to one of the mapped contract
        '''
        if (port.contract is not self.contract) or (port.contract is not self.other_contract):
            raise PortMappingError()

    def add(self, port, mapped_base_name):
        '''
        Add the new constraint
        '''
        self._validate_port(port)
        try:
            self.mapping[mapped_base_name] = port
        except KeyError:
            self.mapping[mapped_base_name] = set()

    def connect(self, port, other_port, mapped_name=None):
        '''
        Connects two ports.
        It means that the ports will be connected to the same
        new port
        '''
        self._validate_port(port)
        self._validate_port(other_port)

        if mapped_name is None:
            mapped_name = port.base_name

        self.mapping[mapped_name].add(port)
        self.mapping[mapped_name].add(other_port)

    def find_conflicts(self):
        '''
        detects possible name conflicts
        '''
        #find ports with same name
        #assuming that there are no ports with the same name in the same contract
        #this means that at most 2 ports have the same name

        #all_ports_pool = dict(self.contract.ports_dict.viewitems() +
        #                      self.other_contract.ports_dict.viewitem())

        cross_diff_1 = (self.contract.input_ports_dict.viewkeys() &
                        self.other_contract.output_ports_dict.viewkeys())
        cross_diff_2 = (self.contract.output_ports_dict.viewkeys() &
                        self.other_contract.input_ports_dict.viewkeys())
        input_diff = (self.contract.input_ports_dict.viewkeys() &
                      self.other_contract.input_ports_dict.viewkeys())
        output_diff = (self.contract.output_ports_dict.viewkeys() &
                       self.other_contract.output_ports_dict.viewkeys())

        total_diff = cross_diff_1 | cross_diff_2 | input_diff | output_diff
        conflict_ports_1 = {name: self.contract.ports_dict[name] for name in total_diff}
        conflict_ports_2 = {name: self.other_contract.ports_dict[name] for name in total_diff}

        #reverse_map = self.reverse_mapping

        #for name in total_diff:
        #    port_1 = conflict_ports_1[name]
        #    port_2 = conflict_ports_2[name]
        #    #conflicting names not in the mapping set
        #    if (port_1 not in reverse_map) and (port_2 not in reverse_map):
        #        raise PortMappingError()
        #    else:
        #        #at least one in mapping, we can work on it
        #        if ((port_1 in reverse_map) and
        #            (reverse_map[port_1] != name) and
        #            (name not in self.mapping)):
        #        #add port_2 to mapping with its own name
        #            self.add(port_2, name)
        #        elif ((port_2 in reverse_map) and
        #            (reverse_map[port_2] != name) and
        #            (name not in self.mapping)):
        #            self.add(port_1, name)
        #        else:
        #            raise PortMappingError()

        return [(conflict_ports_1[name], conflict_ports_2[name]) for name in total_diff]



    def define_composed_contract_ports(self):
        '''
        Identifies and defines the input and output ports of the composed
        contract.
        Raises an exception in case of conflicts.
        Ports mapped on the same port will be connected.
        In case of missing mapping, this method will try to automatically
        derive new contract ports in case of no conflict.
        '''

        new_input_ports = {}
        new_output_ports = {}

        #associate new var for performance (reverse_mapping is computed each time)
        reverse_map = self.reverse_mapping

        #returns a set of tuples
        conflict_set = self.find_conflicts()

        for (port, other_port) in conflict_set:

            if not (port in reverse_map and other_port in reverse_map):
                #this means a conflict is not explicitely solved
                raise PortMappingError()

        #connect and check port consistency
        for name, port_set in self.mapping:

            #we need to connects all the ports in port_set
            #error if we try to connect mulptiple outputs

            outputs = [port for port in port_set if port.is_output]

            if len(outputs) > 1:
                raise PortConnectionError('cannot connect multiple outputs')
            else:
                #merge port literals
                port = reduce(lambda x, y: x.merge(y), port_set)

                if len(outputs) == 0:
                    #all inputs -> input
                    new_input_ports[name] = Port(name, literal=port.literal, context=self.context)
                else:
                    #1 output -> output
                    new_output_ports[name] = Port(name, literal=port.leteral, context=self.context)


        #complete with implicit ports from contracts
        #we have disjoint ports or ports which have been previously connected
        #however we are sure, from the previous step, that there are not conflicting
        #port names
        input_pool = dict(self.contract.input_ports_dict.viewitems() |
                          self.other_contract.input_ports_dict.viewitems())
        output_pool = dict(self.contract.output_ports_dict.viewitems() |
                           self.other_contract.output_ports_dict.viewitems())

        implicit_inputs_names = ((self.contract.input_ports_dict.viewkeys() |
                                  self.other_contract.input_ports_dict.viewkeys()) -
                                 self.mapping.viewkeys())
        implicit_output_names = ((self.contract.output_ports_dict.viewkeys() |
                                  self.other_contract.output_ports_dict.viewkeys()) -
                                 self.mapping.viewkeys())

        filtered_inputs = implicit_inputs_names - implicit_output_names

        for name in filtered_inputs:
            #also, check for feedback loops and do not add inputs in case
            if not any([input_pool[name].is_connected(port) for port in output_pool.viewvalues()]):
                new_input_ports[name] = Port(name, literal=input_pool[name].literal,
                                             context=self.context)
        for name in implicit_output_names:
            new_output_ports[name] = Port(name, literal=output_pool[name].literal,
                                          context=self.context)


        return (new_input_ports, new_output_ports)


    @property
    def reverse_mapping(self):
        '''
        Returns a dictionary with port as key and mapped name as value
        '''
        return {port: name for port in port_set for (name, port_set) in self.mapping.viewitems()}


class NonCompositeContractError(Exception):
    '''
    Raised when accessing the origin_contract property
    but contract is not obtained as a composition of others
    '''
    pass

class PortDeclarationError(Exception):
    '''
    Raised if there are incosistencies in port declaration
    '''
    pass

class PortMappingError(Exception):
    '''
    Raised if a formula uses an undeclared port
    '''
    pass

class PortNotFoundError(Exception):
    '''
    Raised if a port name is not found
    '''
    pass

class PortConnectionError(Exception):
    '''
    Raised in case of attemp of connecting two output ports
    '''