"""
Tests that emulate the debugger adaptor and just test the interaction between
the front end and back end API classes.

Tests:
Client -> Server -> APIDispatcher
"""

import tempfile
import sys
import json
import time
import logging
import subprocess
import base64

from mock import Mock
from nose.tools import *

import voltron
from voltron.core import *
from voltron.api import *
from voltron.plugin import PluginManager, DebuggerAdaptorPlugin

import platform
if platform.system() == 'Darwin':
    sys.path.append("/Applications/Xcode.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python")

from common import *

log = logging.getLogger(__name__)

class APIHostNotSupportedRequest(APIRequest):
    @server_side
    def dispatch(self):
        return APIDebuggerHostNotSupportedErrorResponse()


class APIHostNotSupportedPlugin(APIPlugin):
    request = "host_not_supported"
    request_class = APIHostNotSupportedRequest
    response_class = APIResponse


def setup():
    global server, client, target, pm, adaptor, methods

    log.info("setting up API tests")

    # set up voltron
    voltron.setup_env()
    pm = PluginManager()
    plugin = pm.debugger_plugin_for_host('lldb')
    adaptor = plugin.adaptor_class()
    voltron.debugger = adaptor

    # update the thingy
    inject_mock(adaptor)

    # start up a voltron server
    server = Server(plugin_mgr=pm, debugger=adaptor)
    server.start()

    time.sleep(0.1)

    # set up client
    client = Client()
    client.connect()

def teardown():
    server.stop()

def make_direct_request(request):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(voltron.env['sock'])
    sock.send(request)
    data = sock.recv(0xFFFF)
    return data

def test_direct_invalid_json():
    data = make_direct_request('xxx')
    res = APIResponse(data=data)
    assert res.is_error
    assert res.error_code == 0x1001

def test_front_end_bad_request():
    req = pm.api_plugins['version'].request_class()
    req.request = 'xxx'
    res = client.send_request(req)
    assert res.is_error
    assert res.error_code == 0x1002

def test_front_end_host_not_supported():
    req = pm.api_plugins['host_not_supported'].request_class()
    res = client.send_request(req)
    assert res.is_error
    assert res.error_code == 0x1003

def test_backend_version():
    res = pm.api_plugins['version'].request_class().dispatch()
    assert res.data['api_version'] == 1.0
    assert res.data['host_version'] == 'lldb-something'

def test_direct_version():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "version"
        }
    ))
    res = pm.api_plugins['version'].response_class(data)
    assert res.data['api_version'] == 1.0
    assert res.data['host_version'] == 'lldb-something'

def test_frontend_version():
    req = pm.api_plugins['version'].request_class()
    res = client.send_request(req)
    assert res.data['api_version'] == 1.0
    assert res.data['host_version'] == 'lldb-something'

def test_backend_state():
    res = pm.api_plugins['state'].request_class().dispatch()
    assert res.is_success
    assert res.data["state"] == "stopped"

def test_direct_state():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "state"
        }
    ))
    res = pm.api_plugins['state'].response_class(data)
    assert res.is_success
    assert res.state == "stopped"

def test_frontend_state():
    req = pm.api_plugins['state'].request_class()
    res = client.send_request(req)
    assert res.is_success
    assert res.state == "stopped"

def test_frontend_state_with_id():
    req = pm.api_plugins['state'].request_class()
    req.data['target_id'] = 0
    res = client.send_request(req)
    assert res.is_success
    assert res.state == "stopped"

def test_frontend_wait_timeout():
    req = pm.api_plugins['wait'].request_class(timeout=2)
    res = client.send_request(req)
    assert res.is_error

def test_backend_list_targets():
    res = pm.api_plugins['list_targets'].request_class().dispatch()
    assert res.is_success
    assert res.data["targets"] == targets_response

def test_direct_list_targets():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "list_targets"
        }
    ))
    res = pm.api_plugins['list_targets'].response_class(data=data)
    assert res.is_success
    assert res.data["targets"] == targets_response

def test_frontend_list_targets():
    req = pm.api_plugins['list_targets'].request_class()
    res = client.send_request(req)
    assert res.is_success
    assert res.data["targets"] == targets_response

def test_backend_read_registers():
    res = pm.api_plugins['read_registers'].request_class().dispatch()
    assert res.is_success
    assert res.data["registers"] == read_registers_response

def test_direct_read_registers():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "read_registers"
        }
    ))
    res = pm.api_plugins['read_registers'].response_class(data)
    assert res.is_success
    assert res.data["registers"] == read_registers_response

def test_frontend_read_registers():
    req = pm.api_plugins['read_registers'].request_class()
    res = client.send_request(req)
    assert res.is_success
    assert res.data["registers"] == read_registers_response

def test_backend_read_memory():
    res = pm.api_plugins['read_memory'].request_class(address=0x1000, length=0x40).dispatch()
    assert res.is_success
    assert res.memory == read_memory_response

def test_direct_read_memory():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "read_memory",
            "data": {
                "target_id": 0,
                "address": 0x1000,
                "length": 0x40
            }
        }
    ))
    res = pm.api_plugins['read_memory'].response_class(data)
    assert res.is_success
    assert res.memory == read_memory_response

def test_frontend_read_memory():
    req = pm.api_plugins['read_memory'].request_class(0x1000, 0x40)
    res = client.send_request(req)
    assert res.is_success
    assert res.memory == read_memory_response

def test_backend_read_stack():
    res = pm.api_plugins['read_stack'].request_class(length=0x40).dispatch()
    assert res.is_success
    assert res.memory == read_stack_response

def test_direct_read_stack():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "read_stack",
            "data": {
                "target_id": 0,
                "length": 0x40
            }
        }
    ))
    res = pm.api_plugins['read_stack'].response_class(data)
    assert res.is_success
    assert res.memory == read_stack_response

def test_frontend_read_stack():
    req = pm.api_plugins['read_stack'].request_class(0x40)
    res = client.send_request(req)
    assert res.is_success
    assert res.memory == read_stack_response

def test_backend_execute_command():
    res = pm.api_plugins['execute_command'].request_class("reg read").dispatch()
    assert res.is_success
    assert res.output == execute_command_response

def test_direct_execute_command():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "execute_command",
            "data": {
                "command": "reg read"
            }
        }
    ))
    res = pm.api_plugins['execute_command'].response_class(data)
    assert res.is_success
    assert res.output == execute_command_response

def test_frontend_execute_command():
    req = pm.api_plugins['execute_command'].request_class("reg read")
    res = client.send_request(req)
    assert res.is_success
    assert res.output == execute_command_response

def test_backend_disassemble():
    res = pm.api_plugins['disassemble'].request_class(count=16).dispatch()
    assert res.is_success
    assert res.disassembly == disassemble_response

def test_direct_disassemble():
    data = make_direct_request(json.dumps(
        {
            "type":         "request",
            "request":      "disassemble",
            "data": {"count": 16}
        }
    ))
    res = pm.api_plugins['disassemble'].response_class(data)
    assert res.is_success
    assert res.disassembly == disassemble_response

def test_frontend_disassemble():
    req = pm.api_plugins['disassemble'].request_class(count=16)
    res = client.send_request(req)
    assert res.is_success
    assert res.disassembly == disassemble_response
