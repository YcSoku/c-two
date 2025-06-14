import sys
import zmq
import struct
import logging
import threading

# Logging Configuration ###########################################################
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# TODO: Add auto-termination of server subprocess if max idle time is exceeded
class Server:
    def __init__(self, server_address: str, crm_instance: object, name: str = '', timeout: int = 0):
        if name == '':
            name = crm_instance.__class__.__name__
        
        self.name = name
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(server_address)
        self.server_address = server_address
        self.crm = crm_instance
        
        self._idle_timeout = timeout
        self._termination_event = threading.Event()
        self._server_thread = threading.Thread(target=self._run, daemon=True)
    
    def start(self):
        self._server_thread.name = self.name
        self._server_thread.start()
    
    def stop(self):
        self._cleanup(f'Cleaning up CRM Server "{self.name}"...')
        self._termination_event.set()
    
    def wait_for_termination(self, check_interval: float = 0.1):
        if sys.platform != 'win32':
            while not self._termination_event.is_set():
                try:
                    threading.Event().wait(check_interval)
                except KeyboardInterrupt:
                    logger.info('\nKeyboardInterrupt received.\nStopping CRM server...')
                    self._cleanup(f'Cleaning up CRM Server "{self.name}"...')
                    self._termination_event.set()

        else:
            while not self._termination_event.is_set():
                pass
            self._cleanup(f'Cleaning up CRM Server "{self.name}"...')
            self._termination_event.set()
            
    def _run(self):
        try:
            timeout_ms = int(self._idle_timeout * 1000) if self._idle_timeout > 0 else -1
            self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
            while not self._termination_event.is_set():
                try:
                    full_request = self.socket.recv()
                    
                    # Check for PING message
                    if full_request == b'PING':
                        self.socket.send(b'PONG')
                        continue
                    
                    # Check for SHUTDOWN message
                    if full_request == b'SHUTDOWN':
                        self.socket.send(b'SHUTDOWN_ACK')
                        self._termination_event.set()
                        break
                    
                    sub_messages = _parse_message(full_request)
                    if len(sub_messages) != 2:
                        raise ValueError("Expected exactly 2 sub-messages (meta and data)")
                
                    # Get method name 
                    method_name = sub_messages[0].tobytes().decode('utf-8')
                    
                    # Get arguments
                    args_bytes = sub_messages[1]
                    
                    # Call method wrapped from CRM instance method
                    method = getattr(self.crm, method_name)
                    _, response = method(args_bytes)
                    
                    # Send response
                    self.socket.send(response)
                
                except zmq.error.Again:
                    if self._idle_timeout > 0:
                        logger.info(f'Server "{self.name}" idle timeout ({self._idle_timeout}s) exceeded. Terminating server...')
                        self._termination_event.set()
                        break
                    continue
                except zmq.ContextTerminated:
                    break
            
        except Exception as e:
            self._cleanup(f'Error in CRM Server "{self.name}": {e}')

    def _stop(self):
        if hasattr(self, '_server_thread') and self._server_thread.is_alive():
            self._server_thread.join()
        self.socket.close()
        self.context.term()
    
    def _cleanup(self, message: str = ''):
        logger.info(message)
        try:
            self._stop()
            if hasattr(self.crm, 'terminate') and callable(self.crm.terminate):
                self.crm.terminate()
        except Exception as e:
            logger.error(f'Error during termination: {e}')

# Helpers ##################################################

def _parse_message(full_message: bytes) -> list[memoryview]:
    buffer = memoryview(full_message)
    messages = []
    offset = 0
    
    while offset < len(buffer):
        if offset + 8 > len(buffer):
            raise ValueError("Incomplete length prefix at end of message")
        
        length = struct.unpack('>Q', buffer[offset:offset + 8])[0]
        offset += 8
        
        if offset + length > len(buffer):
            raise ValueError(f"Message length {length} exceeds remaining buffer size at offset {offset}")
        
        message = buffer[offset:offset + length]
        messages.append(message)
        offset += length
    
    if offset != len(buffer):
        raise ValueError(f"Extra bytes remaining after parsing: {len(buffer) - offset}")
    
    return messages