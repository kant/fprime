#!/bin/env python
#===============================================================================
# NAME: test_api.py
#
# DESCRIPTION: A basic test framework for integration testing.
# AUTHOR: Kevin Dinkel
# EMAIL:  dinkel@jpl.nasa.gov
# DATE CREATED: November 19, 2015
#
# Copyright 2015, California Institute of Technology.
# ALL RIGHTS RESERVED. U.S. Government Sponsorship acknowledged.
#===============================================================================
#
# Python standard modules

from utils.gse_api import GseApi
from utils.test_history import TestHistory
import signal
import time
import utils.history as history

__author__ = "Kevin Dinkel"
__copyright__ = "Copyright 2015, California Institute of Technology."
__version__ = "1.0"
__email__ = "kevin.dinkel@jpl.nasa.gov"

class TestApi(GseApi, TestHistory):
  '''
  ------------------------------------------------------------------------------------------------
  NOTE: This TestApi extends many super classes. To best see all its methods and descriptions run:

    pydoc test_api

  This will show you all the methods and derived methods included within this API in one place.
  -------------------------------------------------------------------------------------------------

  This TestAPI extends the GSE API by adding three main features:

    1) A set of histories (dictionaries) which store incoming events and telemetry
    2) The ability to assert truths about the state of these histories at any time
    3) The ability to wait for truths about the state of these histories to become true before
       a given timeout

  This module is intended to be used for integration testing. A user will instantiate
  an object of type TestAPI and use it (and the underlying GseApi object) to send commands
  to a running topology. The TestAPI will collect any out coming telemetry and events.
  The user can use the TestAPI to run assertions against the received telemetry and events
  to check that the topology is running as expected.

  There are a few things the user should be aware of: All received events and telemetry are
  received on an incoming message queue. These events and telemetry are not stored into a
  history for querying until a '*wait*" function in this API is run, in which case events and
  telemetry are copied from the message queue and into the history until the "*wait*" function
  returns. Optionally, the user may sleep an arbitrary amount of time, and then run update()
  to force an update of the history from the message queue at a given time. The latter method
  is not as desireable for many reasons, because choosing an arbitrary sleep time can be difficult
  or error prone. After the histories are filled during a test, the user can run "*assert*" functions
  to check the state of the histories, without worrying about the histories updating as the check them.
  Finally, the user can then (optionally) clear the history before sending more commands to the topology.

  Here is a very basic test that someone might write using this API:

    def test_single_command(api):
      # This is a very basic test. Send a noop command and make sure it succeeds.

      # Wait for FSW to be started, and clear the state of the api:
      time.sleep(2)
      api.reset()

      # Send no-op and make sure we get a response within 5 seconds:
      api.send("CMD_NO_OP") # Command is sent, this returns immediately
      api.wait_assert_evr_size(1, "OpCodeCompleted") # Collect data in history until this evr is returned

      # Assert that we got events signaling the success of the command:
      api.assert_evr_size(1, "OpCodeDispatched") # Check that 1 event of these types have been received
      api.assert_evr_size(1, "OpCodeCompleted")
      api.assert_evr_size(1, "NoOpReceived")

      # Assert that the correct command was executed:
      noOpId = api.get_cmd_id("CMD_NO_OP") # get the command id (opcode) from the mnemonic,
                                           # since the opcode is an event parameter we want to check
      api.assert_evr([noOpId, api.ANYTHING], "OpCodeDispatched") # Check event with two arguments,
                                                                 # but ignore the value of the second one
      api.assert_evr([noOpId], "OpCodeCompleted") # Check event with single argument
      api.assert_evr([noOpId], "OpCodeCompleted", index=api.ALL) # This is equivelant to the first command
                                                                 # we are making sure all events of this type
                                                                 # have this value
      api.assert_evr([noOpId], "OpCodeCompleted", index=0) # Check only the first index
      api.assert_evr([noOpId], "OpCodeCompleted", index=api.ANY) # Using api.ANY can be helpful if you want
                                                                 # check that any index matches the expected value

      # Assert that we got telemetry signaling the success of the command:
      api.assert_tlm_size(1, "CommandsDispatched") # Check that one telemetry of this type has been received

      # Size assertion functions also have an optional filterFunc argument that can be used
      # to only count telemetry or events that pass a certain filter function. In this case
      # we would expect that there are 0 "CommandDispatched" evrs that have a value greater
      # than 1, since only a single command was sent.
      api.assert_tlm_size(0, "CommandsDispatched", filterFunc=(lambda x: x > 1))

      # Assert that the value of the telemetry point is 1:
      api.assert_tlm(1, "CommandsDispatched") # Check that CommandsDispatched count has been
                                              # incremented from 0 to 1
  '''
  ###############################
  # Public API methods:
  ###############################
  def __init__(self, *args, **kwargs):
    super(TestApi, self).__init__(*args, **kwargs)

  ###################################################################################
  ###################################################################################
  ## Sending Commands:
  ###################################################################################
  ###################################################################################
  def send_wait_evr(self, cmd_name, evr_name, args=None, timeout=5):
    '''
    Send a command and update histories until a given event is received on the message queue
    Note: no test assertions are thrown during the execution of this command, even in the
    event of a timeout
    @param cmd_name: the name (mnemonic) of the command to send
    @param evr_name: the name of the event to wait for
    @param args: (optional) arguments to pass with the command
    @param timeout: (optional) timeout in seconds, default is 5 seconds
    '''
    status = self.send(cmd_name, args)
    if status == -1:
      return [], []
    tlm_list, evr_list = super(TestApi, self).wait_evr(evr_name, timeout)
    self.__add_to_hist(tlm_list, evr_list)

  def send_wait_tlm(self, cmd_name, tlm_name, args=None, timeout=5):
    '''
    Send a command and update histories until a given telemetry point is received on the message queue
    Note: no test assertions are thrown during the execution of this command, even in the
    event of a timeout
    @param cmd_name: the name (mnemonic) of the command to send
    @param tlm_name: the name of the tlm to wait for
    @param args: (optional) arguments to pass with the command
    @param timeout: (optional) timeout in seconds, default is 5 seconds
    '''
    status = self.send(cmd_name, args)
    if status == -1:
      return [], []
    tlm_list, evr_list = super(TestApi, self).wait_tlm(tlm_name, timeout)
    self.__add_to_hist(tlm_list, evr_list)

  ###################################################################################
  ###################################################################################
  ## Updating histories:
  ###################################################################################
  ###################################################################################
  def wait_evr(self, evr_name, timeout=5):
    '''
    Update histories until a given event is received on the message queue
    Note: no test assertions are thrown during the execution of this command, even in the
    event of a timeout, use wait_assert* commands to achieve this.
    @param evr_name: the name of the evr to wait for
    @param timeout: (optional) timeout in seconds, default is 5 seconds
    '''
    tlm_list, evr_list = super(TestApi, self).wait_evr(evr_name, timeout)
    self.__add_to_hist(tlm_list, evr_list)

  def wait_tlm(self, tlm_name, timeout=5):
    '''
    Update histories until a given telemetry point is received on the message queue
    Note: no test assertions are thrown during the execution of this command, even in the
    event of a timeout, use wait_assert* commands to achieve this.
    @param tlm_name: the name of the tlm to wait for
    @param timeout: (optional) timeout in seconds, default is 5 seconds
    '''
    tlm_list, evr_list = super(TestApi, self).wait_tlm(tlm_name, timeout)
    self.__add_to_hist(tlm_list, evr_list)

  def update(self):
    '''
    Update histories right now. This takes any data sitting on the message queues and pushes
    it into the histories. This function might be useful when running command, sleeping a
    predetermined amount of time, and then running update_hist(). It is an alternative to
    the "wait_*" and "wait_assert_*" functions in this API, but should be used sparingly
    as it might create brittle tests.
    Note: no test assertions are thrown during the execution of this command, even in the
    event of a timeout, use wait_assert* commands to achieve this.
    '''
    tlm_list, evr_list = super(TestApi, self).receive()
    self.__add_to_hist(tlm_list, evr_list)

  ###################################################################################
  ###################################################################################
  ## Clear histories:
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # clear_evr(self)
  # clear_tlm(self)
  # clear(self)
  #
  # Reset API state:
  def reset(self):
    '''
    Remove all events from the event history and remove all telemetry from the telemetry history
    and remove any pending events or telemetry in the message queue. This gets rid of ALL the current
    telemetry and event state, and should be useful in providing a clean slate during testing.
    '''
    self.clear()
    super(TestApi, self).flush()
  ###################################################################################
  ###################################################################################
  ## Print helpers:
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # print_evr(self)
  # print_tlm(self)
  # pretty_print(self)
  #
  ###################################################################################
  ###################################################################################
  ## Test event size:
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # assert_evr_size(self, size, evr_name=None)
  # assert_evr_size_eq(self, size, evr_name=None) # Same as above, but here for convenience
  # assert_evr_size_ne(self, size, evr_name=None)
  # assert_evr_size_lt(self, size, evr_name=None)
  # assert_evr_size_le(self, size, evr_name=None)
  # assert_evr_size_gt(self, size, evr_name=None)
  # assert_evr_size_ge(self, size, evr_name=None)
  #
  ###################################################################################
  ###################################################################################
  ## Test telemetry size:
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # assert_tlm_size(self, size, tlm_name=None)
  # assert_tlm_size_eq(self, size, tlm_name=None) # Same as above, but here for convenience
  # assert_tlm_size_ne(self, size, tlm_name=None)
  # assert_tlm_size_lt(self, size, tlm_name=None)
  # assert_tlm_size_le(self, size, tlm_name=None)
  # assert_tlm_size_gt(self, size, tlm_name=None)
  # assert_tlm_size_ge(self, size, tlm_name=None)
  #
  ###################################################################################
  ###################################################################################
  ## Test event values:
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # assert_evr(self, value, evr_name=None, index=history.ALL)
  # assert_evr_eq(self, value, evr_name=None, index=history.ALL) # Same as above, but here for convenience
  # assert_evr_ne(self, value, evr_name=None, index=history.ALL)
  # assert_evr_lt(self, value, evr_name=None, index=history.ALL)
  # assert_evr_le(self, value, evr_name=None, index=history.ALL)
  # assert_evr_gt(self, value, evr_name=None, index=history.ALL)
  # assert_evr_ge(self, value, evr_name=None, index=history.ALL)
  # assert_evr_is(self, value, evr_name=None, index=history.ALL)
  # assert_evr_is_not(self, value, evr_name=None, index=history.ALL)
  #
  ###################################################################################
  ###################################################################################
  ## Test telemetry values:
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # assert_tlm(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_eq(self, value, tlm_name=None, index=history.ALL) # Same as above, but here for convenience
  # assert_tlm_ne(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_lt(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_le(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_gt(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_ge(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_is(self, value, tlm_name=None, index=history.ALL)
  # assert_tlm_is_not(self, value, tlm_name=None, index=history.ALL)
  #

  ###################################################################################
  ###################################################################################
  ## Test and wait for event size:
  ###################################################################################
  ###################################################################################
  def wait_assert_evr_size(self, size, evr_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of events received is equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size(size, evr_name, filterFunc), timeout)

  def wait_assert_evr_size_eq(self, size, evr_name=None, filterFunc=None, timeout=5): # Same as above, but here for convenience
    '''
    Assert the number of events received is equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size_eq(size, evr_name, filterFunc), timeout)

  def wait_assert_evr_size_ne(self, size, evr_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of events received is not equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size_ne(size, evr_name, filterFunc), timeout)

  def wait_assert_evr_size_lt(self, size, evr_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of events received is less than 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size_lt(size, evr_name, filterFunc), timeout)

  def wait_assert_evr_size_le(self, size, evr_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of events received is less than or equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size_le(size, evr_name, filterFunc), timeout)

  def wait_assert_evr_size_gt(self, size, evr_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of events received is greater than 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size_gt(size, evr_name, filterFunc), timeout)

  def wait_assert_evr_size_ge(self, size, evr_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of events received is greater than or equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of events expected
    @param evr_name: (optional) if provided, only check the size of events of
    this type
    @param filterFunc: (optional) if provided, only events arguments that return true when passed
    into this function are counted. For example, to only count event arguments with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_size_ge(size, evr_name, filterFunc), timeout)

  ###################################################################################
  ###################################################################################
  ## Test and wait for telemetry size:
  ###################################################################################
  ###################################################################################
  def wait_assert_tlm_size(self, size, tlm_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of telemetry received is equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size(size, tlm_name, filterFunc), timeout)

  def wait_assert_tlm_size_eq(self, size, tlm_name=None, filterFunc=None, timeout=5): # Same as above, but here for convenience
    '''
    Assert the number of telemetry received is equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size_eq(size, tlm_name, filterFunc), timeout)

  def wait_assert_tlm_size_ne(self, size, tlm_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of telemetry received is not equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size_ne(size, tlm_name, filterFunc), timeout)

  def wait_assert_tlm_size_lt(self, size, tlm_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of telemetry received is less than 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size_lt(size, tlm_name, filterFunc), timeout)

  def wait_assert_tlm_size_le(self, size, tlm_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of telemetry received is less than or equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size_le(size, tlm_name, filterFunc), timeout)

  def wait_assert_tlm_size_gt(self, size, tlm_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of telemetry received is greater than 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size_gt(size, tlm_name, filterFunc), timeout)

  def wait_assert_tlm_size_ge(self, size, tlm_name=None, filterFunc=None, timeout=5):
    '''
    Assert the number of telemetry received is greater than or equal to 'size' or wait until this
    is true, otherwise timeout and assert failure.
    @param size: the number of telemetry points expected
    @param tlm_name: (optional) if provided, only check the size of telemetry of
    this type
    @param filterFunc: (optional) if provided, only telemetry values that return true when passed
    into this function are counted. For example, to only count telemetry values with numerical values
    greater than 5 you can pass in the function: filterFunc=(lambda x: x>5)
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_size_ge(size, tlm_name, filterFunc), timeout)

  ###################################################################################
  ###################################################################################
  ## Test and wait for event argument values:
  ###################################################################################
  ###################################################################################
  def wait_assert_evr(self, value, evr_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of event arguments received is equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr(value, evr_name, index), timeout)

  def wait_assert_evr_eq(self, value, evr_name=None, index=history.ALL, timeout=5): # Same as above, but here for convenience
    '''
    Assert the value of event arguments received is equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_eq(value, evr_name, index), timeout)

  def wait_assert_evr_ne(self, value, evr_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of event arguments received is not equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_ne(value, evr_name, index), timeout)

  def wait_assert_evr_lt(self, value, evr_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of event arguments received is less than 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_lt(value, evr_name, index), timeout)

  def wait_assert_evr_le(self, value, evr_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of event arguments received is less than or equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_le(value, evr_name, index), timeout)

  def wait_assert_evr_gt(self, value, evr_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of event arguments received is greater than 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_gt(value, evr_name, index), timeout)

  def wait_assert_evr_ge(self, value, evr_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of event arguments received is greater than or equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the event arguments
    @param evr_name: (optional) if provided, only check the value of events
    of this type
    @param index: (optional) if provided, only check the value of events of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if evr_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_evr_ge(value, evr_name, index), timeout)

  ###################################################################################
  ###################################################################################
  ## Test and wait for telemtry values:
  ###################################################################################
  ###################################################################################
  def wait_assert_tlm(self, value, tlm_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of telemetry received is equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm(value, tlm_name, index), timeout)

  def wait_assert_tlm_eq(self, value, tlm_name=None, index=history.ALL, timeout=5): # Same as above, but here for convenience
    '''
    Assert the value of telemetry received is equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_eq(value, tlm_name, index), timeout)

  def wait_assert_tlm_ne(self, value, tlm_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of telemetry received is not equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_ne(value, tlm_name, index), timeout)

  def wait_assert_tlm_lt(self, value, tlm_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of telemetry received is less than 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_lt(value, tlm_name, index), timeout)

  def wait_assert_tlm_le(self, value, tlm_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of telemetry received is less than or equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_le(value, tlm_name, index), timeout)

  def wait_assert_tlm_gt(self, value, tlm_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of telemetry received is greater than 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_gt(value, tlm_name, index), timeout)

  def wait_assert_tlm_ge(self, value, tlm_name=None, index=history.ALL, timeout=5):
    '''
    Assert the value of telemetry received is greater than or equal to 'value' or
    wait until this is true, otherwise timeout and assert failure
    @param value: the expected value of the telemetry
    @param tlm_name: (optional) if provided, only check the value of telemetry
    of this type
    @param index: (optional) if provided, only check the value of tlm of
    this index in the history. Passing TestHistory.ALL will check all indexes for that value.
    Passing TestHistory.ANY will check to make sure at least 1 value meets the comparison.
    Note index will only be used if tlm_name is also specified.
    @param timeout: (optional) timeout in seconds (default is 5 seconds).
    '''
    return self.__wait_assert(lambda: self.assert_tlm_ge(value, tlm_name, index), timeout)

  ###################################################################################
  ###################################################################################
  ## Retrieve dictionary elements
  ###################################################################################
  ###################################################################################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # get_evr_hist(self, evr_name=None, index=history.ALL)
  # get_tlm_hist(self, tlm_name=None, index=history.ALL)
  #
  ###############################
  # Public class variables:
  ###############################
  #
  # Please see the TestHistory class for the definition of the following inherited methods:
  #
  # anything()
  # near()
  #

  ###############################
  # Private methods:
  ###############################
  def __wait_assert(self, f, timeout=None):
    """
    Continues to update the history until a function f does not assert or a timeout occures
    """

    def add_item_to_hist():
      # Add a single item from the queue to the history
      # Return true if item is added
      tlm, evr = super(TestApi, self)._pop_queue()
      if tlm is None and evr is None:
        return False
      tlm_list = []
      evr_list = []
      if tlm:
        tlm_list.append(tlm)
      if evr:
        evr_list.append(evr)
      self.__add_to_hist(tlm_list, evr_list)
      return True

    def fail(msg):
      try:
        f()
      except AssertionError as e:
        assert 0, msg + "\n\n\n" + e.args[0]
      assert 0, msg + "\n\n\n" + self.get_pretty_print()

    def assert_failing():
      # As long as there is something to add to the hist keep trying
      # the assertion, else return True. Return False if the assertion is met
      while True:
        try:
          f()
        except AssertionError:
          if add_item_to_hist():
            continue
          else:
            return True
        except:
          raise
        return False

    if timeout:
      signal.signal(signal.SIGALRM, self._timeout_sig_handler)
      signal.alarm(timeout)

    try:
      while assert_failing():
        # Sleep a bit if there is nothing in the queue, and then try again:
        if timeout:
          time.sleep(0.1)
        else:
          # just check assertion once if a timeout is not set
          fail('Unable to meet assertion.')
    except self.TimeoutException:
      fail('Timeout reached, unable to meet assertion.')
    except:
      raise

    if timeout:
      signal.alarm(0)

  def __add_to_hist(self, tlms=[], evrs=[]):
    # Translate ids to names:
    evrs = [(self._events.getNameDict()[p[0]],p[1]) for p in evrs]
    tlms = [(self._channels.getNameDict()[p[0]],p[1]) for p in tlms]
    super(TestApi, self).add(evrs, tlms)

