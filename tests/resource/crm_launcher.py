import os
import sys
import signal
import logging
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src/')))

import c_two as cc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_RESOURCE_DIR = Path(os.getcwd()).resolve() / 'tests' / 'resource'
MOCK_CRM_LAUNCHER_PY = TEST_RESOURCE_DIR / 'mock.crm.py'
CRM_PROCESS: subprocess.Popen = None

def start_mock_crm():
    global CRM_PROCESS
    # Platform-specific subprocess arguments
    kwargs = {}
    if sys.platform != 'win32':
        # Unix-specific: create new process group
        kwargs['preexec_fn'] = os.setsid
    else:
        # Windows-specific: don't open a new console window
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    
    cmd = [
        sys.executable,
        MOCK_CRM_LAUNCHER_PY,
    ]
    
    CRM_PROCESS = subprocess.Popen(
        cmd,
        **kwargs
    )

    while cc.message.Client.ping('tcp://localhost:5555') is False:
        pass

    logger.info(f'Mock CRM process started with PID: {CRM_PROCESS.pid}')

def stop_mock_crm():
    global CRM_PROCESS
    if cc.message.Client.shutdown('tcp://localhost:5555', 0.5, CRM_PROCESS):
        
        logger.info(f'Mock CRM process stopped with PID: {CRM_PROCESS.pid}')
    else:
        logger.error('Failed to stop the Mock CRM process.')

if __name__ == '__main__':
    start_mock_crm()
    stop_mock_crm()
