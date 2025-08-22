#!/usr/bin/env python3
"""
EchoNet Hosting - Complete Platform Consolidated into Single File
Memory Limit: 1GB RAM | Storage Limit: 1GB | All components embedded
"""

import os
import sys
import json
import logging
import time
import signal
import subprocess
import psutil
import zipfile
import shutil
import base64
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import venv
import resource

from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# =============================================================================
# CONFIGURATION AND CONSTANTS
# =============================================================================

# Memory and Storage Limits (1GB each)
MAX_MEMORY_MB = 1024  # 1GB
MAX_STORAGE_MB = 1024  # 1GB
PASSCODE = "67234"
PROJECTS_DIR = "projects"
ALLOWED_EXTENSIONS = {'py', 'txt', 'html', 'css', 'js', 'json', 'md', 'yml', 'yaml'}

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('echonet.log')
    ]
)

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Ensure projects directory exists
os.makedirs(PROJECTS_DIR, exist_ok=True)

# App start time for uptime tracking
APP_START_TIME = time.time()

# =============================================================================
# SYSTEM RESOURCE MONITORING AND LIMITS
# =============================================================================

class ResourceManager:
    """Manages system resources with 1GB limits for RAM and storage"""
    
    def __init__(self):
        self.max_memory_bytes = MAX_MEMORY_MB * 1024 * 1024
        self.max_storage_bytes = MAX_STORAGE_MB * 1024 * 1024
        
    def check_memory_limit(self) -> bool:
        """Check if memory usage is within limit"""
        try:
            process = psutil.Process()
            memory_usage = process.memory_info().rss
            return memory_usage <= self.max_memory_bytes
        except Exception as e:
            logging.error(f"Error checking memory: {e}")
            return True
    
    def check_storage_limit(self) -> bool:
        """Check if storage usage is within limit"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(PROJECTS_DIR):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
            return total_size <= self.max_storage_bytes
        except Exception as e:
            logging.error(f"Error checking storage: {e}")
            return True
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0
    
    def get_storage_usage(self) -> float:
        """Get current storage usage in MB"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(PROJECTS_DIR):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
            return total_size / (1024 * 1024)
        except Exception:
            return 0.0
    
    def enforce_limits(self):
        """Enforce resource limits - stop operations if exceeded"""
        if not self.check_memory_limit():
            logging.critical("Memory limit exceeded! Stopping new processes.")
            return False
        if not self.check_storage_limit():
            logging.critical("Storage limit exceeded! Preventing new files.")
            return False
        return True

# Global resource manager
resource_manager = ResourceManager()

# =============================================================================
# GITHUB INTEGRATION MANAGER
# =============================================================================

class GitHubManager:
    """Manages GitHub repository integration for project storage using requests module"""
    
    def __init__(self):
        self.access_token = "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"
        self.repo_url = "https://github.com/Tenoco/EchoNetHosting"
        self.repo_name = "Tenoco/EchoNetHosting"
        self.api_base_url = "https://api.github.com"
        self.projects_dir = PROJECTS_DIR
        
        # Setup headers for GitHub API requests
        self.headers = {
            'Authorization': f'token {self.access_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }
        
        # Test GitHub connection
        try:
            import requests
            self.requests = requests
            # Test connection by getting repository info
            response = self.requests.get(
                f"{self.api_base_url}/repos/{self.repo_name}",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                self.available = True
                logging.info("GitHub integration initialized successfully")
            else:
                self.available = False
                logging.error(f"GitHub connection failed: {response.status_code}")
        except Exception as e:
            self.available = False
            logging.error(f"Failed to initialize GitHub integration: {e}")
    
    def is_available(self) -> bool:
        """Check if GitHub integration is available"""
        return self.available
    
    def sync_project_to_github(self, project_name: str) -> bool:
        """Sync a project directory to GitHub repository using requests"""
        if not self.is_available():
            logging.error("GitHub integration not available")
            return False
        
        try:
            project_path = os.path.join(self.projects_dir, project_name)
            if not os.path.exists(project_path):
                logging.error(f"Project path not found: {project_path}")
                return False
            
            # Get all files in the project
            for root, dirs, files in os.walk(project_path):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    # Calculate relative path from projects directory
                    relative_path = os.path.relpath(local_file_path, self.projects_dir)
                    github_path = f"projects/{relative_path}".replace(os.sep, '/')
                    
                    # Read file content
                    with open(local_file_path, 'rb') as f:
                        content = f.read()
                    
                    # Sync file to GitHub
                    self._create_or_update_file(github_path, content, f"Update {file} in {project_name}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error syncing project {project_name} to GitHub: {e}")
            return False
    
    def sync_file_to_github(self, project_name: str, filename: str) -> bool:
        """Sync a specific file to GitHub repository using requests"""
        if not self.is_available():
            logging.error("GitHub integration not available")
            return False
        
        try:
            local_file_path = os.path.join(self.projects_dir, project_name, filename)
            if not os.path.exists(local_file_path):
                logging.error(f"File not found: {local_file_path}")
                return False
            
            github_path = f"projects/{project_name}/{filename}".replace(os.sep, '/')
            
            # Read file content
            with open(local_file_path, 'rb') as f:
                content = f.read()
            
            # Sync file to GitHub
            return self._create_or_update_file(github_path, content, f"Update {filename} in {project_name}")
            
        except Exception as e:
            logging.error(f"Error syncing file {filename} from {project_name} to GitHub: {e}")
            return False
    
    def _create_or_update_file(self, github_path: str, content: bytes, message: str) -> bool:
        """Create or update a file in GitHub using requests API"""
        try:
            import base64
            
            # Check if file exists first
            file_info = self._get_file_info(github_path)
            
            # Prepare data
            data = {
                "message": message,
                "content": base64.b64encode(content).decode('utf-8')
            }
            
            if file_info:
                # File exists, update it
                data["sha"] = file_info["sha"]
            
            # Create or update file
            response = self.requests.put(
                f"{self.api_base_url}/repos/{self.repo_name}/contents/{github_path}",
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                action = "Updated" if file_info else "Created"
                logging.info(f"{action} {github_path} in GitHub")
                return True
            else:
                logging.error(f"Failed to sync {github_path}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error syncing {github_path}: {e}")
            return False
    
    def _get_file_info(self, github_path: str):
        """Get file information from GitHub"""
        try:
            response = self.requests.get(
                f"{self.api_base_url}/repos/{self.repo_name}/contents/{github_path}",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None
    
    def delete_file_from_github(self, project_name: str, filename: str) -> bool:
        """Delete a file from GitHub repository using requests"""
        if not self.is_available():
            logging.error("GitHub integration not available")
            return False
        
        try:
            github_path = f"projects/{project_name}/{filename}".replace(os.sep, '/')
            
            # Get file info to get SHA
            file_info = self._get_file_info(github_path)
            if not file_info:
                logging.warning(f"File {github_path} not found in GitHub")
                return True  # Already deleted
            
            # Delete file
            data = {
                "message": f"Delete {filename} from {project_name}",
                "sha": file_info["sha"]
            }
            
            response = self.requests.delete(
                f"{self.api_base_url}/repos/{self.repo_name}/contents/{github_path}",
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                logging.info(f"Deleted {github_path} from GitHub")
                return True
            else:
                logging.error(f"Failed to delete {github_path}: {response.status_code}")
                return False
            
        except Exception as e:
            logging.error(f"Error deleting file {filename} from {project_name} in GitHub: {e}")
            return False
    
    def sync_from_github(self) -> bool:
        """Sync all projects from GitHub to local storage using requests"""
        if not self.is_available():
            logging.error("GitHub integration not available")
            return False
        
        try:
            # Get all contents from the projects directory in GitHub
            response = self.requests.get(
                f"{self.api_base_url}/repos/{self.repo_name}/contents/projects",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 404:
                # Projects directory doesn't exist yet
                logging.info("Projects directory doesn't exist in GitHub yet")
                return True
            elif response.status_code != 200:
                logging.error(f"Error getting projects directory: {response.status_code}")
                return False
            
            contents = response.json()
            
            # Process each project
            for item in contents:
                if item.get("type") == "dir":
                    project_name = item["name"]
                    self._sync_project_from_github(project_name)
            
            return True
            
        except Exception as e:
            logging.error(f"Error syncing from GitHub: {e}")
            return False
    
    def _sync_project_from_github(self, project_name: str) -> bool:
        """Sync a specific project from GitHub using requests"""
        try:
            project_github_path = f"projects/{project_name}"
            local_project_path = os.path.join(self.projects_dir, project_name)
            
            # Create local project directory
            os.makedirs(local_project_path, exist_ok=True)
            
            # Get all files in the project from GitHub
            response = self.requests.get(
                f"{self.api_base_url}/repos/{self.repo_name}/contents/{project_github_path}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logging.error(f"Error getting project {project_name}: {response.status_code}")
                return False
            
            contents = response.json()
            
            def download_contents(contents_list, base_path=""):
                for content in contents_list:
                    if content.get("type") == "file":
                        # Download file
                        file_path = os.path.join(base_path, content["name"]) if base_path else content["name"]
                        local_file_path = os.path.join(local_project_path, file_path)
                        
                        # Create subdirectories if needed
                        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                        
                        # Download file content
                        file_response = self.requests.get(content["download_url"], timeout=30)
                        if file_response.status_code == 200:
                            with open(local_file_path, 'wb') as f:
                                f.write(file_response.content)
                            logging.info(f"Downloaded {content['name']} for project {project_name}")
                    elif content.get("type") == "dir":
                        # Create subdirectory and download its contents
                        subdir_path = os.path.join(base_path, content["name"]) if base_path else content["name"]
                        subdir_response = self.requests.get(
                            f"{self.api_base_url}/repos/{self.repo_name}/contents/{content['path']}",
                            headers=self.headers,
                            timeout=30
                        )
                        if subdir_response.status_code == 200:
                            download_contents(subdir_response.json(), subdir_path)
            
            download_contents(contents if isinstance(contents, list) else [contents])
            return True
            
        except Exception as e:
            logging.error(f"Error syncing project {project_name} from GitHub: {e}")
            return False
    
    def update_project_main_file(self, project_name: str, new_main_file: str) -> bool:
        """Update the main file setting for a project and sync to GitHub"""
        try:
            echonet_path = os.path.join(self.projects_dir, project_name, 'echonet.json')
            
            if os.path.exists(echonet_path):
                with open(echonet_path, 'r') as f:
                    config = json.load(f)
                
                # Update main file
                if 'runtime' in config:
                    config['runtime']['main_file'] = new_main_file
                else:
                    config['main_file'] = new_main_file
                
                # Save updated config
                with open(echonet_path, 'w') as f:
                    json.dump(config, f, indent=2)
                
                # Sync to GitHub
                self.sync_file_to_github(project_name, 'echonet.json')
                logging.info(f"Updated main file for {project_name} to {new_main_file}")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error updating main file for {project_name}: {e}")
            return False
    
    def delete_project_from_github(self, project_name: str) -> bool:
        """Delete a project from GitHub repository using requests"""
        if not self.is_available():
            logging.error("GitHub integration not available")
            return False
        
        try:
            # Get all files in the project directory
            project_github_path = f"projects/{project_name}"
            
            response = self.requests.get(
                f"{self.api_base_url}/repos/{self.repo_name}/contents/{project_github_path}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 404:
                logging.info(f"Project {project_name} not found in GitHub")
                return True  # Already deleted or never existed
            elif response.status_code != 200:
                logging.error(f"Error getting project contents: {response.status_code}")
                return False
            
            contents = response.json()
            
            # Delete all files in the project directory
            def delete_contents(contents_list):
                for content in contents_list:
                    if content.get("type") == "file":
                        # Delete file
                        data = {
                            "message": f"Delete {content['name']} from {project_name}",
                            "sha": content["sha"]
                        }
                        
                        delete_response = self.requests.delete(
                            f"{self.api_base_url}/repos/{self.repo_name}/contents/{content['path']}",
                            headers=self.headers,
                            json=data,
                            timeout=30
                        )
                        
                        if delete_response.status_code == 200:
                            logging.info(f"Deleted {content['name']} from project {project_name} in GitHub")
                    elif content.get("type") == "dir":
                        # Get subdirectory contents and delete recursively
                        subdir_response = self.requests.get(
                            f"{self.api_base_url}/repos/{self.repo_name}/contents/{content['path']}",
                            headers=self.headers,
                            timeout=30
                        )
                        if subdir_response.status_code == 200:
                            delete_contents(subdir_response.json())
            
            delete_contents(contents if isinstance(contents, list) else [contents])
            
            logging.info(f"Successfully deleted project {project_name} from GitHub")
            return True
            
        except Exception as e:
            logging.error(f"Error deleting project {project_name} from GitHub: {e}")
            return False

# Global GitHub manager
github_manager = GitHubManager()

# Sync projects from GitHub on startup
try:
    if github_manager.is_available():
        logging.info("Syncing projects from GitHub on startup...")
        github_manager.sync_from_github()
        logging.info("GitHub sync completed successfully")
        
        # Auto-start previously active projects (will be done after ProcessManager is initialized)
        pass
    else:
        logging.info("GitHub not available - working in local mode")
        # Auto-start will be done after ProcessManager is initialized
except Exception as e:
    logging.error(f"Error syncing from GitHub on startup: {e}")

# =============================================================================
# PROJECT TEMPLATES AND TYPES
# =============================================================================

PROJECT_TYPES = {
    'flask': {
        'name': 'Flask Web Application',
        'description': 'Traditional web application with templates and forms',
        'icon': '🌐',
        'color': 'primary',
        'difficulty': 'Beginner',
        'setup_time': '~2 minutes',
        'requirements': ['flask==3.0.0', 'werkzeug==3.0.1', 'gunicorn==21.2.0'],
        'main_file': 'app.py',
        'startup_command': 'python app.py'
    },
    'fastapi': {
        'name': 'FastAPI Modern API',
        'description': 'High-performance API with automatic documentation',
        'icon': '⚡',
        'color': 'info',
        'difficulty': 'Intermediate',
        'setup_time': '~3 minutes',
        'requirements': ['fastapi==0.104.1', 'uvicorn==0.24.0'],
        'main_file': 'main.py',
        'startup_command': 'uvicorn main:app --host 0.0.0.0 --port 8001'
    },
    'telegram_bot': {
        'name': 'Telegram Bot',
        'description': 'Chat bot for Telegram messaging platform',
        'icon': '🤖',
        'color': 'warning',
        'difficulty': 'Intermediate',
        'setup_time': '~2 minutes',
        'requirements': ['python-telegram-bot==20.7', 'requests==2.31.0'],
        'main_file': 'bot.py',
        'startup_command': 'python bot.py'
    },
    'python_script': {
        'name': 'Python Script',
        'description': 'General purpose Python application or script',
        'icon': '🐍',
        'color': 'dark',
        'difficulty': 'Beginner',
        'setup_time': '~1 minute',
        'requirements': ['requests==2.31.0'],
        'main_file': 'main.py',
        'startup_command': 'python main.py'
    }
}

# =============================================================================
# PROCESS MANAGER
# =============================================================================

class ProcessManager:
    def __init__(self):
        self.processes_file = "running_processes.json"
        self.processes = self._load_processes()
        self.projects_dir = PROJECTS_DIR
        self._cleanup_dead_processes()
    
    def _load_processes(self):
        """Load running processes from file"""
        try:
            if os.path.exists(self.processes_file):
                with open(self.processes_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"Error loading processes: {e}")
            return {}
    
    def _save_processes(self):
        """Save running processes to file"""
        try:
            with open(self.processes_file, 'w') as f:
                json.dump(self.processes, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving processes: {e}")
    
    def _cleanup_dead_processes(self):
        """Clean up processes that are no longer running"""
        dead_projects = []
        for project_name, process_info in self.processes.items():
            try:
                pid = process_info.get('pid')
                if pid and not psutil.pid_exists(pid):
                    dead_projects.append(project_name)
            except Exception:
                dead_projects.append(project_name)
        
        for project_name in dead_projects:
            logging.info(f"Cleaning up dead process for project: {project_name}")
            del self.processes[project_name]
        
        if dead_projects:
            self._save_processes()
    
    def start_project(self, project_name):
        """Start a project with resource limit checks"""
        if not resource_manager.enforce_limits():
            logging.error(f"Cannot start {project_name}: Resource limits exceeded")
            return False
            
        try:
            if project_name in self.processes:
                logging.warning(f"Project {project_name} is already running")
                return True
            
            project_path = os.path.join(self.projects_dir, project_name)
            if not os.path.exists(project_path):
                logging.error(f"Project path not found: {project_path}")
                return False
            
            # Read project info - check both echonet.json and project_info.json
            echonet_file = os.path.join(project_path, 'echonet.json')
            project_file = os.path.join(project_path, 'project_info.json')
            
            if os.path.exists(echonet_file):
                with open(echonet_file, 'r') as f:
                    project_info = json.load(f)
            elif os.path.exists(project_file):
                with open(project_file, 'r') as f:
                    project_info = json.load(f)
            else:
                project_info = {'type': 'python_script', 'main_file': 'main.py'}
            
            # Find next available port
            port = self._find_available_port()
            if not port:
                logging.error("No available ports for project")
                return False
            
            # Start process - auto-detect main file if not specified
            main_file = project_info.get('main_file')
            if not main_file:
                # Auto-detect main file by checking common entry points
                for candidate in ['app.py', 'bot.py', 'main.py', 'run.py', 'server.py']:
                    candidate_path = os.path.join(project_path, candidate)
                    if os.path.exists(candidate_path):
                        main_file = candidate
                        break
                
                if not main_file:
                    logging.error(f"No main file found in project: {project_path}")
                    return False
            
            main_path = os.path.join(project_path, main_file)
            if not os.path.exists(main_path):
                logging.error(f"Main file not found: {main_path}")
                return False
            
            # Create startup command - handle missing type gracefully
            project_type = project_info.get('type', 'python_script')
            startup_cmd = self._get_startup_command(project_type, main_file, port)
            
            # Create log file for real-time output
            log_file_path = os.path.join(project_path, 'console.log')
            
            # Start the process and capture output to log file
            with open(log_file_path, 'w') as log_file:
                log_file.write(f"=== Project {project_name} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                log_file.write(f"Command: {startup_cmd}\n")
                log_file.write(f"Working directory: {project_path}\n")
                log_file.write("="*60 + "\n\n")
                log_file.flush()
                
            process = subprocess.Popen(
                startup_cmd,
                cwd=project_path,
                stdout=open(log_file_path, 'a'),
                stderr=subprocess.STDOUT,
                shell=True,
                bufsize=0,  # Unbuffered for real-time output
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            # Store process info
            self.processes[project_name] = {
                'pid': process.pid,
                'port': port,
                'started': datetime.now().isoformat(),
                'type': project_type,
                'status': 'running',
                'log_file': log_file_path
            }
            
            self._save_processes()
            self._save_active_projects()  # Save active projects list
            logging.info(f"Started project {project_name} on port {port}")
            return True
            
        except Exception as e:
            logging.error(f"Error starting project {project_name}: {e}")
            return False
    
    def _save_active_projects(self):
        """Save list of active projects directly to GitHub (no local storage)"""
        try:
            active_projects = list(self.processes.keys())
            active_projects_data = {
                'active_projects': active_projects,
                'last_updated': datetime.now().isoformat()
            }
            
            # Save directly to GitHub without local storage
            if github_manager.is_available():
                try:
                    content = json.dumps(active_projects_data, indent=2).encode('utf-8')
                    
                    # Upload directly to GitHub root using requests
                    if github_manager._create_or_update_file('active_projects.json', content, 'Update active projects list'):
                        logging.info("Updated active_projects.json in GitHub")
                    else:
                        logging.error("Failed to update active_projects.json in GitHub")
                except Exception as e:
                    logging.error(f"Error syncing active_projects.json to GitHub: {e}")
            else:
                logging.warning("GitHub not available - cannot save active projects")
                
        except Exception as e:
            logging.error(f"Error saving active projects: {e}")
    
    def _load_active_projects(self):
        """Load and auto-start active projects directly from GitHub (no local storage)"""
        temp_file = None
        try:
            # Read directly from GitHub without local storage
            if github_manager.is_available():
                try:
                    # Get active_projects.json from GitHub using requests
                    response = github_manager.requests.get(
                        f"{github_manager.api_base_url}/repos/{github_manager.repo_name}/contents/active_projects.json",
                        headers=github_manager.headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        import base64
                        file_content = response.json()
                        decoded_content = base64.b64decode(file_content['content']).decode('utf-8')
                        
                        # Use temporary file that will be cleaned up
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_f:
                            temp_file = temp_f.name
                            temp_f.write(decoded_content)
                    else:
                        logging.info(f"No active_projects.json in GitHub yet: {response.status_code}")
                        return
                    
                    # Read from temporary file
                    with open(temp_file, 'r') as f:
                        data = json.load(f)
                    
                    # Clean up temporary file immediately
                    os.unlink(temp_file)
                    temp_file = None
                    
                    active_projects = data.get('active_projects', [])
                    if active_projects:
                        logging.info(f"Auto-starting {len(active_projects)} previously active projects from GitHub...")
                        
                        for project_name in active_projects:
                            if project_name not in self.processes:  # Don't restart if already running
                                project_path = os.path.join(self.projects_dir, project_name)
                                if os.path.exists(project_path):
                                    logging.info(f"Auto-starting project: {project_name}")
                                    self.start_project(project_name)
                                else:
                                    logging.warning(f"Cannot auto-start {project_name}: project not found")
                    else:
                        logging.info("No active projects to auto-start")
                        
                except Exception as e:
                    logging.info(f"No active_projects.json in GitHub yet or error reading: {e}")
            else:
                logging.info("GitHub not available - cannot load active projects")
                        
        except Exception as e:
            logging.error(f"Error loading active projects: {e}")
        finally:
            # Cleanup temporary file if it still exists
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass
    
    def stop_project(self, project_name):
        """Stop a running project"""
        try:
            if project_name not in self.processes:
                logging.warning(f"Project {project_name} is not running")
                return False
            
            process_info = self.processes[project_name]
            pid = process_info.get('pid')
            
            if not pid or not psutil.pid_exists(pid):
                del self.processes[project_name]
                self._save_processes()
                return True
            
            try:
                # Try to terminate gracefully
                if os.name == 'nt':  # Windows
                    os.kill(pid, signal.SIGTERM)
                else:  # Unix/Linux
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                
                # Wait briefly for termination
                start_time = time.time()
                while time.time() - start_time < 5:
                    if not psutil.pid_exists(pid):
                        break
                    time.sleep(0.1)
                
                # Force kill if still running
                if psutil.pid_exists(pid):
                    if os.name == 'nt':
                        os.kill(pid, signal.SIGKILL)
                    else:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                
                del self.processes[project_name]
                self._save_processes()
                self._save_active_projects()  # Update active projects list
                logging.info(f"Successfully stopped project {project_name}")
                return True
                
            except ProcessLookupError:
                del self.processes[project_name]
                self._save_processes()
                self._save_active_projects()  # Update active projects list
                return True
                
        except Exception as e:
            logging.error(f"Error stopping project {project_name}: {e}")
            return False
    
    def _find_available_port(self, start_port=8001):
        """Find an available port starting from start_port"""
        for port in range(start_port, start_port + 100):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', port))
                    return port
            except OSError:
                continue
        return None
    
    def _get_startup_command(self, project_type, main_file, port):
        """Get startup command for project type"""
        if project_type == 'flask':
            return f"python {main_file}"
        elif project_type == 'fastapi':
            return f"uvicorn {main_file.replace('.py', '')}:app --host 0.0.0.0 --port {port}"
        else:
            return f"python {main_file}"
    
    def is_project_running(self, project_name):
        """Check if a project is running"""
        if project_name not in self.processes:
            return False
        
        pid = self.processes[project_name].get('pid')
        if not pid:
            return False
        
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False
    
    def get_project_status(self, project_name):
        """Get detailed status for a project"""
        if not self.is_project_running(project_name):
            return {
                'status': 'stopped',
                'pid': None,
                'port': None,
                'started': None,
                'uptime': 0,
                'memory_usage': 0,
                'cpu_percent': 0
            }
        
        process_info = self.processes[project_name]
        pid = process_info.get('pid')
        
        try:
            proc = psutil.Process(pid)
            started = datetime.fromisoformat(process_info['started'])
            uptime = (datetime.now() - started).total_seconds()
            
            return {
                'status': 'running',
                'pid': pid,
                'port': process_info.get('port'),
                'started': process_info['started'],
                'uptime': uptime,
                'memory_usage': proc.memory_info().rss / (1024 * 1024),  # MB
                'cpu_percent': proc.cpu_percent()
            }
        except Exception:
            return {
                'status': 'stopped',
                'pid': None,
                'port': None,
                'started': None,
                'uptime': 0,
                'memory_usage': 0,
                'cpu_percent': 0
            }
    
    def get_project_logs(self, project_name, lines=50):
        """Get real-time project logs from console output"""
        try:
            # Primary source: Real-time console.log from running process
            console_log = os.path.join(self.projects_dir, project_name, 'console.log')
            
            if os.path.exists(console_log):
                try:
                    with open(console_log, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().strip()
                        if content:
                            if lines and lines > 0:
                                log_lines = content.split('\n')
                                return '\n'.join(log_lines[-lines:])
                            return content
                except Exception as read_error:
                    logging.warning(f"Error reading console log: {read_error}")
            
            # Fallback: Check other log sources
            fallback_sources = [
                os.path.join(self.projects_dir, project_name, 'app.log'),
                os.path.join(self.projects_dir, project_name, 'output.log'),
                os.path.join(self.projects_dir, project_name, 'server.log')
            ]
            
            for log_file in fallback_sources:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read().strip()
                            if content:
                                if lines and lines > 0:
                                    log_lines = content.split('\n')
                                    return '\n'.join(log_lines[-lines:])
                                return content
                    except Exception as read_error:
                        logging.warning(f"Error reading {log_file}: {read_error}")
            
            # Return status based on project state
            if self.is_project_running(project_name):
                return f"Project {project_name} is running...\nReal-time output will appear here when the script produces output.\n\nTo see output, make sure your script uses print() statements or logging."
            else:
                return f"Project {project_name} is not running.\nStart the project to see real-time console output here."
            
        except Exception as e:
            logging.error(f"Error reading logs for {project_name}: {e}")
            return f"Error accessing logs: {str(e)}"

# Global process manager
process_manager = ProcessManager()

# Cleanup any local temporary files from previous sessions
def cleanup_local_temp_files():
    """Remove any local temporary files that should not persist"""
    temp_files = ['active_projects.json', 'running_projects.json']
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                logging.info(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logging.warning(f"Could not clean up {temp_file}: {e}")

# Initialize ProcessManager and auto-start active projects
try:
    # Clean up any temporary files first
    cleanup_local_temp_files()
    
    # Auto-start active projects now that ProcessManager is initialized
    process_manager._load_active_projects()
except Exception as e:
    logging.error(f"Error auto-starting projects: {e}")

# =============================================================================
# EMBEDDED HTML TEMPLATES
# =============================================================================

BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}EchoNet Hosting{% endblock %}</title>
    <meta name="description" content="EchoNet - Professional hosting platform for Python applications">
    <meta name="keywords" content="hosting, python, flask, fastapi, telegram bot">
    <meta name="author" content="EchoNet Hosting Platform">
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <!-- Font Awesome Icons -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    
    <!-- Inter Font -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <!-- Custom CSS -->
    <style>
    :root {
        --primary-color: #0d6efd;
        --secondary-color: #6c757d;
        --success-color: #198754;
        --info-color: #0dcaf0;
        --warning-color: #ffc107;
        --danger-color: #dc3545;
        --light-color: #f8f9fa;
        --dark-color: #212529;
    }
    
    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        line-height: 1.6;
        color: var(--dark-color);
    }
    
    .auth-main {
        min-height: 100vh;
        display: flex;
        align-items: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .auth-main .card {
        border-radius: 1rem;
        backdrop-filter: blur(10px);
        background: rgba(255, 255, 255, 0.95);
    }
    
    .navbar-brand {
        font-size: 1.5rem;
    }
    
    .navbar-nav .nav-link {
        font-weight: 500;
    }
    
    .card {
        border: 0;
        border-radius: 0.75rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        transition: all 0.3s ease;
    }
    
    .card:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
    
    .stat-card {
        background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
    }
    
    .stat-icon {
        width: 48px;
        height: 48px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 1.2rem;
    }
    
    .btn {
        font-weight: 500;
        border-radius: 0.5rem;
        transition: all 0.3s ease;
    }
    
    .btn-primary {
        background: linear-gradient(135deg, var(--primary-color) 0%, #0b5ed7 100%);
        border: none;
    }
    
    .btn-primary:hover {
        background: linear-gradient(135deg, #0b5ed7 0%, var(--primary-color) 100%);
        transform: translateY(-1px);
    }
    
    .btn-success {
        background: linear-gradient(135deg, var(--success-color) 0%, #157347 100%);
        border: none;
    }
    
    .btn-danger {
        background: linear-gradient(135deg, var(--danger-color) 0%, #bb2d3b 100%);
        border: none;
    }
    
    .table th {
        font-weight: 600;
        border-top: 0;
        color: var(--dark-color);
    }
    
    .table-hover tbody tr:hover {
        background-color: rgba(13, 110, 253, 0.05);
    }
    
    .badge {
        font-weight: 500;
        letter-spacing: 0.5px;
    }
    
    .form-control {
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
        transition: all 0.3s ease;
    }
    
    .form-control:focus {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 0.2rem rgba(13, 110, 253, 0.1);
    }
    
    .modal-content {
        border-radius: 1rem;
        border: 0;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
    }
    
    .alert {
        border-radius: 0.75rem;
        border: 0;
        font-weight: 500;
    }
    
    .breadcrumb {
        background: transparent;
        padding: 0;
        margin-bottom: 1rem;
    }
    
    .breadcrumb-item a {
        color: var(--primary-color);
        text-decoration: none;
    }
    
    footer {
        border-top: 1px solid rgba(0, 0, 0, 0.05);
        margin-top: auto;
    }
    
    /* Mobile Responsive */
    @media (max-width: 768px) {
        .container {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }
        
        .btn-group {
            display: flex;
            flex-wrap: wrap;
            gap: 0.25rem;
            width: 100%;
        }
        
        .btn-group .btn {
            flex: 1;
            min-width: auto;
            margin-bottom: 0.25rem;
            font-size: 0.875rem;
            padding: 0.375rem 0.5rem;
        }
        
        .stat-card {
            margin-bottom: 0.75rem;
        }
        
        .stat-icon {
            width: 40px;
            height: 40px;
            font-size: 1rem;
        }
        
        h1 {
            font-size: 1.5rem;
        }
        
        .col-auto .btn-group {
            flex-direction: column;
            width: 100%;
        }
        
        .modal-dialog {
            margin: 1rem;
            max-width: calc(100% - 2rem);
        }
        
        .form-control {
            font-size: 16px;
        }
    }
    
    @media (max-width: 576px) {
        .col-lg-2 {
            flex: 0 0 100%;
            max-width: 100%;
        }
        
        .btn {
            padding: 0.5rem 0.75rem;
            font-size: 0.875rem;
        }
    }
    
    /* Console specific styles */
    .console-output {
        background-color: #1e1e1e;
        color: #d4d4d4;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 14px;
        line-height: 1.4;
        height: 500px;
        overflow-y: auto;
        border-radius: 0 0 0.375rem 0.375rem;
    }
    
    .console-text {
        margin: 0;
        padding: 0;
        background: transparent;
        border: none;
        color: inherit;
        font-family: inherit;
        font-size: inherit;
        line-height: inherit;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    
    .status-indicator {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
    
    .log-error { color: #ef4444; }
    .log-warning { color: #fbbf24; }
    .log-info { color: #60a5fa; }
    .log-success { color: #4ade80; }
    
    @media (max-width: 768px) {
        .console-output {
            height: 400px;
            font-size: 12px;
        }
    }
    </style>
</head>
<body>
    <!-- Navigation -->
    {% if session.authenticated %}
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="{{ url_for('dashboard') }}">
                <i class="fas fa-server me-2"></i>EchoNet Hosting
            </a>
            
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('dashboard') }}">
                            <i class="fas fa-tachometer-alt me-1"></i>Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('logout') }}">
                            <i class="fas fa-sign-out-alt me-1"></i>Logout
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>
    {% endif %}

    <!-- Flash Messages -->
    <div class="container mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <!-- Main Content -->
    <main class="{% if not session.authenticated %}auth-main{% endif %}">
        {% block content %}{% endblock %}
    </main>

    <!-- Footer -->
    <footer class="bg-light text-center py-4 mt-5">
        <div class="container">
            <p class="mb-0 text-muted">&copy; 2025 EchoNet Hosting. Private hosting platform.</p>
        </div>
    </footer>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    
    {% block scripts %}{% endblock %}
</body>
</html>'''

LOGIN_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - EchoNet Hosting</title>
    <meta name="description" content="EchoNet - Professional hosting platform for Python applications">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-color: #0d6efd;
            --secondary-color: #6c757d;
            --success-color: #198754;
            --info-color: #0dcaf0;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --light-color: #f8f9fa;
            --dark-color: #212529;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            line-height: 1.6;
            color: var(--dark-color);
        }
        .auth-main {
            min-height: 100vh;
            display: flex;
            align-items: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .card {
            border: 0;
            border-radius: 1rem;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
            background: rgba(255, 255, 255, 0.95);
        }
        .btn-primary {
            background: linear-gradient(135deg, var(--primary-color) 0%, #0b5ed7 100%);
            border: none;
            font-weight: 500;
            border-radius: 0.5rem;
            transition: all 0.3s ease;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #0b5ed7 0%, var(--primary-color) 100%);
            transform: translateY(-1px);
        }
        .form-control {
            border-radius: 0.5rem;
            border: 1px solid #dee2e6;
            transition: all 0.3s ease;
        }
        .form-control:focus {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 0.2rem rgba(13, 110, 253, 0.1);
        }
        .input-group-text {
            border-radius: 0.5rem 0 0 0.5rem;
        }
        .alert {
            border-radius: 0.75rem;
            border: 0;
            font-weight: 500;
        }
        @media (max-width: 768px) {
            .container { padding-left: 0.75rem; padding-right: 0.75rem; }
            .form-control { font-size: 16px; }
        }
    </style>
</head>
<body>
    <main class="auth-main">
        <!-- Flash Messages -->
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="container position-absolute w-100" style="top: 20px; z-index: 1050;">
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                            {{ message }}
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        </div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-6 col-lg-4">
                    <div class="card shadow-lg border-0">
                        <div class="card-body p-5">
                            <div class="text-center mb-4">
                                <i class="fas fa-server fa-3x text-primary mb-3"></i>
                                <h2 class="fw-bold">EchoNet Hosting</h2>
                                <p class="text-muted">Enter your passcode to continue</p>
                            </div>
                            
                            <form method="POST">
                                <div class="mb-4">
                                    <label for="passcode" class="form-label">Passcode</label>
                                    <div class="input-group">
                                        <span class="input-group-text">
                                            <i class="fas fa-lock"></i>
                                        </span>
                                        <input type="password" 
                                               class="form-control" 
                                               id="passcode" 
                                               name="passcode" 
                                               placeholder="Enter passcode" 
                                               required 
                                               autofocus>
                                    </div>
                                </div>
                                
                                <button type="submit" class="btn btn-primary w-100 py-2">
                                    <i class="fas fa-sign-in-alt me-2"></i>Access Dashboard
                                </button>
                            </form>
                            
                            <div class="mt-4 text-center">
                                <small class="text-muted">
                                    <i class="fas fa-info-circle me-1"></i>
                                    Memory: {{ memory_usage }}MB / {{ memory_limit }}MB | 
                                    Storage: {{ storage_usage }}MB / {{ storage_limit }}MB
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''

DASHBOARD_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - EchoNet Hosting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-color: #0d6efd;
            --secondary-color: #6c757d;
            --success-color: #198754;
            --info-color: #0dcaf0;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --light-color: #f8f9fa;
            --dark-color: #212529;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            line-height: 1.6;
            color: var(--dark-color);
        }
        .card {
            border: 0;
            border-radius: 0.75rem;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            transition: all 0.3s ease;
        }
        .card:hover {
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        .stat-card {
            background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
        }
        .stat-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1.2rem;
        }
        .btn {
            font-weight: 500;
            border-radius: 0.5rem;
            transition: all 0.3s ease;
        }
        .btn-primary {
            background: linear-gradient(135deg, var(--primary-color) 0%, #0b5ed7 100%);
            border: none;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #0b5ed7 0%, var(--primary-color) 100%);
            transform: translateY(-1px);
        }
        .btn-success {
            background: linear-gradient(135deg, var(--success-color) 0%, #157347 100%);
            border: none;
        }
        .btn-danger {
            background: linear-gradient(135deg, var(--danger-color) 0%, #bb2d3b 100%);
            border: none;
        }
        .table th {
            font-weight: 600;
            border-top: 0;
            color: var(--dark-color);
        }
        .table-hover tbody tr:hover {
            background-color: rgba(13, 110, 253, 0.05);
        }
        .badge {
            font-weight: 500;
            letter-spacing: 0.5px;
        }
        .form-control {
            border-radius: 0.5rem;
            border: 1px solid #dee2e6;
            transition: all 0.3s ease;
        }
        .form-control:focus {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 0.2rem rgba(13, 110, 253, 0.1);
        }
        .modal-content {
            border-radius: 1rem;
            border: 0;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        }
        .alert {
            border-radius: 0.75rem;
            border: 0;
            font-weight: 500;
        }
        .breadcrumb {
            background: transparent;
            padding: 0;
            margin-bottom: 1rem;
        }
        .breadcrumb-item a {
            color: var(--primary-color);
            text-decoration: none;
        }
        @media (max-width: 768px) {
            .container { padding-left: 0.75rem; padding-right: 0.75rem; }
            .btn-group { display: flex; flex-wrap: wrap; gap: 0.25rem; width: 100%; }
            .btn-group .btn { flex: 1; min-width: auto; margin-bottom: 0.25rem; font-size: 0.875rem; padding: 0.375rem 0.5rem; }
            .stat-card { margin-bottom: 0.75rem; }
            .stat-icon { width: 40px; height: 40px; font-size: 1rem; }
            h1 { font-size: 1.5rem; }
            .col-auto .btn-group { flex-direction: column; width: 100%; }
            .modal-dialog { margin: 1rem; max-width: calc(100% - 2rem); }\
            .form-control { font-size: 16px; }
        }
        @media (max-width: 576px) {
            .col-lg-2 { flex: 0 0 100%; max-width: 100%; }
            .btn { padding: 0.5rem 0.75rem; font-size: 0.875rem; }
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="{{ url_for('dashboard') }}">
                <i class="fas fa-server me-2"></i>EchoNet Hosting
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('dashboard') }}">
                            <i class="fas fa-tachometer-alt me-1"></i>Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('logout') }}">
                            <i class="fas fa-sign-out-alt me-1"></i>Logout
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Flash Messages -->
    <div class="container mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <!-- Main Content -->
<div class="container py-4">
    <!-- Dashboard Header -->
    <div class="row mb-4">
        <div class="col">
            <h1 class="fw-bold mb-2">
                <i class="fas fa-tachometer-alt text-primary me-2"></i>Dashboard
            </h1>
            <p class="text-muted">Manage your projects and monitor your hosting platform</p>
        </div>
        <div class="col-auto">
            <a href="{{ url_for('create_project') }}" class="btn btn-primary">
                <i class="fas fa-plus me-2"></i>New Project
            </a>
        </div>
    </div>

    <!-- Resource Usage Warning -->
    {% if stats.memory_warning or stats.storage_warning %}
    <div class="row mb-4">
        <div class="col">
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Resource Warning:</strong>
                {% if stats.memory_warning %}Memory usage is high ({{ stats.total_ram_usage }}MB / 1024MB). {% endif %}
                {% if stats.storage_warning %}Storage usage is high ({{ stats.total_storage }}MB / 1024MB). {% endif %}
                Consider cleaning up unused projects.
            </div>
        </div>
    </div>
    {% endif %}

    <!-- Stats Cards -->
    <div class="row mb-5">
        <div class="col-lg-2 col-md-4 col-sm-6 mb-3">
            <div class="card stat-card h-100">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h4 class="fw-bold mb-1">{{ stats.total_projects }}</h4>
                            <p class="text-muted mb-0 small">Total Projects</p>
                        </div>
                        <div class="stat-icon bg-primary">
                            <i class="fas fa-folder"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-lg-2 col-md-4 col-sm-6 mb-3">
            <div class="card stat-card h-100">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h4 class="fw-bold mb-1">{{ stats.running_projects }}</h4>
                            <p class="text-muted mb-0 small">Running</p>
                        </div>
                        <div class="stat-icon bg-success">
                            <i class="fas fa-play"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-lg-2 col-md-4 col-sm-6 mb-3">
            <div class="card stat-card h-100">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h4 class="fw-bold mb-1">{{ stats.total_files }}</h4>
                            <p class="text-muted mb-0 small">Total Files</p>
                        </div>
                        <div class="stat-icon bg-info">
                            <i class="fas fa-file"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-lg-2 col-md-4 col-sm-6 mb-3">
            <div class="card stat-card h-100">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h4 class="fw-bold mb-1 {{ 'text-warning' if stats.storage_warning else '' }}">{{ stats.total_storage }}MB</h4>
                            <p class="text-muted mb-0 small">Storage (1GB Max)</p>
                        </div>
                        <div class="stat-icon bg-warning">
                            <i class="fas fa-hdd"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-lg-2 col-md-4 col-sm-6 mb-3">
            <div class="card stat-card h-100">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h4 class="fw-bold mb-1 {{ 'text-danger' if stats.memory_warning else '' }}">{{ stats.total_ram_usage }}MB</h4>
                            <p class="text-muted mb-0 small">RAM (1GB Max)</p>
                        </div>
                        <div class="stat-icon bg-danger">
                            <i class="fas fa-memory"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-lg-2 col-md-4 col-sm-6 mb-3">
            <div class="card stat-card h-100">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h4 class="fw-bold mb-1">{{ stats.system_uptime }}</h4>
                            <p class="text-muted mb-0 small">Uptime</p>
                        </div>
                        <div class="stat-icon bg-secondary">
                            <i class="fas fa-clock"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Quick Actions -->
    <div class="row mb-4">
        <div class="col-md-6 mb-3">
            <div class="card">
                <div class="card-body">
                    <h6 class="card-title mb-3">
                        <i class="fas fa-server text-primary me-2"></i>System Resources
                    </h6>
                    <div class="row text-center">
                        <div class="col-6">
                            <div class="border-end">
                                <h5 class="mb-1">{{ stats.total_ram_usage }}/1024 MB</h5>
                                <small class="text-muted">Memory Usage</small>
                                <div class="progress mt-2" style="height: 6px;">
                                    <div class="progress-bar bg-{{ 'danger' if stats.memory_warning else 'primary' }}" style="width: {{ stats.memory_percent }}%"></div>
                                </div>
                            </div>
                        </div>
                        <div class="col-6">
                            <h5 class="mb-1">{{ stats.total_storage }}/1024 MB</h5>
                            <small class="text-muted">Storage Usage</small>
                            <div class="progress mt-2" style="height: 6px;">
                                <div class="progress-bar bg-{{ 'warning' if stats.storage_warning else 'success' }}" style="width: {{ stats.storage_percent }}%"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-6 mb-3">
            <div class="card">
                <div class="card-body">
                    <h6 class="card-title mb-3">
                        <i class="fas fa-cogs text-success me-2"></i>Quick Actions
                    </h6>
                    <div class="d-flex flex-wrap gap-2">
                        <button class="btn btn-success btn-sm" onclick="startAllProjects()">
                            <i class="fas fa-play me-1"></i>Start All
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="stopAllProjects()">
                            <i class="fas fa-stop me-1"></i>Stop All
                        </button>
                        <button class="btn btn-warning btn-sm" onclick="restartAllProjects()">
                            <i class="fas fa-sync me-1"></i>Restart All
                        </button>
                        <button class="btn btn-info btn-sm" data-bs-toggle="modal" data-bs-target="#importProjectModal">
                            <i class="fas fa-upload me-1"></i>Import ZIP
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Projects List -->
    <div class="row">
        <div class="col">
            <div class="card">
                <div class="card-header bg-white d-flex justify-content-between align-items-center">
                    <h5 class="mb-0 fw-bold">
                        <i class="fas fa-list me-2"></i>Projects
                    </h5>
                    <div>
                        <a href="/create_project" class="btn btn-primary btn-sm">
                            <i class="fas fa-plus"></i> Create Project
                        </a>
                    </div>
                </div>
                <div class="card-body p-0">
                    {% if projects %}
                        <div class="table-responsive">
                            <table class="table table-hover mb-0">
                                <thead class="table-light">
                                    <tr>
                                        <th>Project Name</th>
                                        <th>Type</th>
                                        <th>Status</th>
                                        <th>Memory</th>
                                        <th>Created</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for project in projects %}
                                    <tr>
                                        <td>
                                            <div class="d-flex align-items-center">
                                                {% if project.type == 'flask' %}
                                                    <i class="fas fa-globe text-success me-2"></i>
                                                {% elif project.type == 'telegram_bot' %}
                                                    <i class="fas fa-robot text-info me-2"></i>
                                                {% elif project.type == 'fastapi' %}
                                                    <i class="fas fa-bolt text-danger me-2"></i>
                                                {% else %}
                                                    <i class="fas fa-code text-primary me-2"></i>
                                                {% endif %}
                                                <strong>{{ project.name }}</strong>
                                            </div>
                                        </td>
                                        <td>
                                            <span class="badge bg-{{ project.color }}">{{ project.type_name }}</span>
                                        </td>
                                        <td>
                                            {% if project.status == 'running' %}
                                                <span class="badge bg-success">
                                                    <i class="fas fa-play me-1"></i>Running
                                                </span>
                                            {% else %}
                                                <span class="badge bg-secondary">
                                                    <i class="fas fa-stop me-1"></i>Stopped
                                                </span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            <small class="text-muted">
                                                {% if project.status == 'running' %}
                                                    {{ "%.1f"|format(project.memory_usage) }} MB
                                                {% else %}
                                                    —
                                                {% endif %}
                                            </small>
                                        </td>
                                        <td>
                                            <small class="text-muted">{{ project.created_date }}</small>
                                        </td>
                                        <td>
                                            <div class="btn-group btn-group-sm">
                                                {% if project.status == 'running' %}
                                                    <a href="{{ url_for('stop_project', project_name=project.name) }}" 
                                                       class="btn btn-outline-danger btn-sm">
                                                        <i class="fas fa-stop"></i>
                                                    </a>
                                                    <a href="/app/{{ project.name }}" 
                                                       target="_blank" 
                                                       class="btn btn-outline-primary btn-sm">
                                                        <i class="fas fa-external-link-alt"></i>
                                                    </a>
                                                {% else %}
                                                    <a href="{{ url_for('start_project', project_name=project.name) }}" 
                                                       class="btn btn-outline-success btn-sm">
                                                        <i class="fas fa-play"></i>
                                                    </a>
                                                {% endif %}
                                                <a href="{{ url_for('project_detail', project_name=project.name) }}" 
                                                   class="btn btn-outline-secondary btn-sm">
                                                    <i class="fas fa-folder"></i>
                                                </a>
                                                <a href="{{ url_for('console', project_name=project.name) }}" 
                                                   class="btn btn-outline-warning btn-sm">
                                                    <i class="fas fa-desktop"></i>
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    {% else %}
                        <div class="text-center py-5">
                            <i class="fas fa-folder-open fa-3x text-muted mb-3"></i>
                            <h5 class="text-muted">No projects yet</h5>
                            <p class="text-muted">Create your first project to get started with EchoNet Hosting</p>
                            <a href="{{ url_for('create_project') }}" class="btn btn-primary">
                                <i class="fas fa-plus me-2"></i>Create Your First Project
                            </a>
                        </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Import Project Modal -->
<div class="modal fade" id="importProjectModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">
                    <i class="fas fa-upload text-primary me-2"></i>Import Project from ZIP
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST" action="{{ url_for('import_project') }}" enctype="multipart/form-data">
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="zip_file" class="form-label">Select ZIP File</label>
                        <input type="file" 
                               class="form-control" 
                               id="zip_file" 
                               name="zip_file" 
                               accept=".zip"
                               required>
                        <div class="form-text">
                            Upload a ZIP file containing your project files.
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-upload me-2"></i>Import Project
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
// Mobile-friendly improvements and project management
document.addEventListener('DOMContentLoaded', function() {
    console.log('EchoNet Hosting initialized');
    
    // Auto-refresh with page visibility API
    let refreshInterval;
    
    function startAutoRefresh() {
        refreshInterval = setInterval(() => {
            if (!document.hidden) {
                location.reload();
            }
        }, 30000);
    }
    
    function stopAutoRefresh() {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
    }
    
    // Handle page visibility changes
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            stopAutoRefresh();
        } else {
            startAutoRefresh();
        }
    });
    
    // Mobile optimizations
    if (window.innerWidth < 768) {
        document.querySelectorAll('.btn-group').forEach(group => {
            group.classList.add('btn-group-vertical');
        });
        
        // Stack cards vertically on mobile
        document.querySelectorAll('.col-lg-2').forEach(col => {
            col.classList.remove('col-lg-2');
            col.classList.add('col-12');
        });
    }
    
    startAutoRefresh();
});

// Bulk project actions
function startAllProjects() {
    if (confirm('Start all stopped projects?')) {
        window.location.href = '/start_all_projects';
    }
}

function stopAllProjects() {
    if (confirm('Stop all running projects?')) {
        window.location.href = '/stop_all_projects';
    }
}

function restartAllProjects() {
    if (confirm('Restart all projects? This will stop and then start all projects.')) {
        window.location.href = '/restart_all_projects';
    }
}
    </script>
    
    <!-- Footer -->
    <footer class="bg-light text-center py-4 mt-5">
        <div class="container">
            <p class="mb-0 text-muted">&copy; 2025 EchoNet Hosting. Private hosting platform.</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_uptime(seconds):
    """Format uptime in seconds to human readable format"""
    if not seconds or seconds < 0:
        return '0s'
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def calculate_project_size(project_path):
    """Calculate total size of a project directory in MB with timeout protection"""
    try:
        import time
        start_time = time.time()
        total_size = 0
        file_count = 0
        max_files = 1000  # Limit to prevent hanging on huge directories
        max_time = 3.0  # 3 seconds max
        
        for root, dirs, files in os.walk(project_path):
            # Check timeout
            if time.time() - start_time > max_time:
                logging.warning(f"Size calculation timeout for {project_path}")
                break
                
            # Skip hidden directories and common cache directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git']]
            
            for file in files:
                if file_count >= max_files or time.time() - start_time > max_time:
                    break
                
                file_path = os.path.join(root, file)
                try:
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
                        file_count += 1
                except (OSError, IOError):
                    continue
            
            if file_count >= max_files:
                break
        
        return round(total_size / (1024 * 1024), 2)  # Convert to MB with 2 decimal places
            
    except Exception as e:
        logging.error(f"Error calculating project size: {e}")
        return 0.0

def format_file_size(size_mb):
    """Format file size in MB to human readable format"""
    if size_mb >= 1024:
        return f"{round(size_mb / 1024, 2)} GB"
    elif size_mb >= 1:
        return f"{size_mb} MB"
    else:
        return f"{round(size_mb * 1024, 1)} KB"

def get_project_stats():
    """Get comprehensive project statistics"""
    try:
        projects = []
        total_files = 0
        running_projects = 0
        
        if os.path.exists(PROJECTS_DIR):
            for project_name in os.listdir(PROJECTS_DIR):
                project_path = os.path.join(PROJECTS_DIR, project_name)
                if os.path.isdir(project_path):
                    # Get project info
                    info_file = os.path.join(project_path, 'echonet.json')
                    if os.path.exists(info_file):
                        with open(info_file, 'r') as f:
                            project_info = json.load(f)
                    else:
                        project_info = {'type': 'python_script', 'name': project_name, 'created': datetime.now().isoformat()}
                    
                    # Count files
                    file_count = 0
                    for root, dirs, files in os.walk(project_path):
                        file_count += len(files)
                    total_files += file_count
                    
                    # Check if running
                    is_running = process_manager.is_project_running(project_name)
                    if is_running:
                        running_projects += 1
                    
                    # Get project status
                    status = process_manager.get_project_status(project_name)
                    
                    # Get project type info
                    project_type = project_info.get('type', 'python_script')
                    type_info = PROJECT_TYPES.get(project_type, PROJECT_TYPES['python_script'])
                    
                    projects.append({
                        'name': project_name,
                        'type': project_type,
                        'type_name': type_info['name'],
                        'color': type_info['color'],
                        'status': 'running' if is_running else 'stopped',
                        'memory_usage': status.get('memory_usage', 0),
                        'created_date': datetime.fromisoformat(project_info.get('created', datetime.now().isoformat())).strftime('%Y-%m-%d'),
                        'file_count': file_count
                    })
        
        # System stats
        memory_usage = resource_manager.get_memory_usage()
        storage_usage = resource_manager.get_storage_usage()
        
        # Get EchoNet app uptime (not system uptime)
        try:
            uptime_seconds = time.time() - APP_START_TIME
            system_uptime = format_uptime(uptime_seconds)
        except Exception:
            system_uptime = "Unknown"
        
        return {
            'projects': projects,
            'total_projects': len(projects),
            'running_projects': running_projects,
            'total_files': total_files,
            'total_storage': round(storage_usage, 2),
            'total_ram_usage': round(memory_usage, 2),
            'system_uptime': system_uptime,
            'memory_percent': min(100, (memory_usage / MAX_MEMORY_MB) * 100),
            'storage_percent': min(100, (storage_usage / MAX_STORAGE_MB) * 100),
            'memory_warning': memory_usage > (MAX_MEMORY_MB * 0.8),  # Warning at 80%
            'storage_warning': storage_usage > (MAX_STORAGE_MB * 0.8),  # Warning at 80%
        }
        
    except Exception as e:
        logging.error(f"Error getting project stats: {e}")
        return {
            'projects': [],
            'total_projects': 0,
            'running_projects': 0,
            'total_files': 0,
            'total_storage': 0,
            'total_ram_usage': 0,
            'system_uptime': "Unknown",
            'memory_percent': 0,
            'storage_percent': 0,
            'memory_warning': False,
            'storage_warning': False,
        }

def create_project_template(project_name, project_type, project_path):
    """Create project template files"""
    try:
        if project_type not in PROJECT_TYPES:
            return False
        
        type_info = PROJECT_TYPES[project_type]
        main_file = type_info['main_file']
        
        # Create project directory
        os.makedirs(project_path, exist_ok=True)
        
        # Create main file based on type
        main_path = os.path.join(project_path, main_file)
        
        if project_type == 'flask':
            content = '''from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def hello():
    return '<h1>Hello from EchoNet!</h1><p>Your Flask app is running successfully.</p>'

@app.route('/about')
def about():
    return '<h1>About</h1><p>This is a Flask application hosted on EchoNet.</p>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=True)
'''
        elif project_type == 'fastapi':
            content = '''from fastapi import FastAPI

app = FastAPI(title="EchoNet FastAPI App")

@app.get("/")
async def root():
    return {"message": "Hello from EchoNet!", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "EchoNet FastAPI"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
'''
        elif project_type == 'telegram_bot':
            content = '''import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Replace with your bot token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Hello! I am your EchoNet Telegram bot. '
        'I am running successfully!'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Available commands:\\n'
        '/start - Start the bot\\n'
        '/help - Show this help message\\n'
        '/status - Check bot status'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Bot is running on EchoNet! ✅')

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    
    print("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
'''
        else:  # python_script
            content = '''#!/usr/bin/env python3
"""
EchoNet Python Script
A simple Python application running on EchoNet Hosting
"""

import time
import datetime

def main():
    print("🐍 Python Script started on EchoNet!")
    print(f"Current time: {datetime.datetime.now()}")
    
    # Your code here
    counter = 0
    while True:
        counter += 1
        print(f"Running... Counter: {counter}")
        time.sleep(10)  # Wait 10 seconds
        
        if counter >= 100:  # Reset counter
            counter = 0

if __name__ == "__main__":
    main()
'''
        
        # Write main file
        with open(main_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Create requirements.txt
        requirements_path = os.path.join(project_path, 'requirements.txt')
        with open(requirements_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(type_info['requirements']))
        
        # Create README.md
        readme_path = os.path.join(project_path, 'README.md')
        readme_content = f'''# {project_name}

{type_info['description']}

## Running on EchoNet

This {type_info['name']} is hosted on EchoNet Hosting platform.

### Main file: {main_file}

### Requirements:
{chr(10).join(f"- {req}" for req in type_info['requirements'])}

### Getting Started:

1. Upload your files to the project directory
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `{type_info['startup_command']}`

Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by EchoNet Hosting
'''
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        # Create project metadata
        metadata = {
            'name': project_name,
            'type': project_type,
            'created': datetime.now().isoformat(),
            'main_file': main_file,
            'startup_command': type_info['startup_command'],
            'version': '1.0.0'
        }
        
        metadata_path = os.path.join(project_path, 'echonet.json')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        logging.info(f"Created {project_type} project: {project_name}")
        return True
        
    except Exception as e:
        logging.error(f"Error creating project template: {e}")
        return False

# Add custom filters to Jinja2
app.jinja_env.filters['format_uptime'] = format_uptime
app.jinja_env.filters['format_file_size'] = format_file_size

# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route('/')
def index():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        passcode = request.form.get('passcode', '')
        if passcode == PASSCODE:
            session['authenticated'] = True
            flash('Welcome to EchoNet Hosting!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid passcode. Please try again.', 'danger')
    
    # Get resource usage for display
    memory_usage = round(resource_manager.get_memory_usage(), 2)
    storage_usage = round(resource_manager.get_storage_usage(), 2)
    
    return render_template_string(LOGIN_TEMPLATE, 
                                memory_usage=memory_usage, 
                                memory_limit=MAX_MEMORY_MB,
                                storage_usage=storage_usage, 
                                storage_limit=MAX_STORAGE_MB)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    stats = get_project_stats()
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats, projects=stats['projects'])

@app.route('/create_project', methods=['GET', 'POST'])
def create_project():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if not resource_manager.enforce_limits():
            flash('Cannot create project: Resource limits exceeded', 'danger')
            return redirect(url_for('dashboard'))
        
        project_name = request.form.get('project_name', '').strip()
        project_type = request.form.get('project_type', 'python_script')
        project_description = request.form.get('project_description', '').strip()
        
        if not project_name:
            flash('Project name is required!', 'danger')
            return redirect(url_for('create_project'))
        
        # Sanitize project name (preserve case)
        project_name = secure_filename(project_name.replace(' ', '-'))
        if not project_name:
            flash('Invalid project name!', 'danger')
            return redirect(url_for('create_project'))
        
        project_path = os.path.join(PROJECTS_DIR, project_name)
        
        # Check if project already exists
        if os.path.exists(project_path):
            flash(f'Project "{project_name}" already exists!', 'warning')
            return redirect(url_for('create_project'))
        
        try:
            # Create project from template
            if create_project_template(project_name, project_type, project_path):
                # Sync project to GitHub
                if github_manager.is_available():
                    if github_manager.sync_project_to_github(project_name):
                        flash(f'Project "{project_name}" created and synced to GitHub successfully!', 'success')
                    else:
                        flash(f'Project "{project_name}" created locally but GitHub sync failed!', 'warning')
                else:
                    flash(f'Project "{project_name}" created locally (GitHub not available)!', 'info')
                
                return redirect(url_for('project_detail', project_name=project_name))
            else:
                flash('Error creating project template', 'danger')
        except Exception as e:
            flash(f'Error creating project: {str(e)}', 'danger')
            logging.error(f'Error creating project {project_name}: {e}')
    
    # GET request - show creation form
    create_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Project - EchoNet Hosting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; }
        .card { border: 0; border-radius: 0.75rem; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05); }
        .btn { font-weight: 500; border-radius: 0.5rem; }
        .btn-primary { background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%); border: none; }
        .form-control { border-radius: 0.5rem; }
        .alert { border-radius: 0.75rem; border: 0; font-weight: 500; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/dashboard">
                <i class="fas fa-server me-2"></i>EchoNet Hosting
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard">
                    <i class="fas fa-arrow-left me-1"></i>Dashboard
                </a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
<div class="container py-4">
    <div class="row justify-content-center">
        <div class="col-md-8">
            <div class="card">
                <div class="card-header">
                    <h4 class="mb-0">
                        <i class="fas fa-plus-circle text-primary me-2"></i>Create New Project
                    </h4>
                </div>
                <div class="card-body">
                    <form method="POST">
                        <div class="mb-3">
                            <label for="project_name" class="form-label">Project Name *</label>
                            <input type="text" class="form-control" id="project_name" name="project_name" 
                                   placeholder="my-awesome-project" required>
                            <div class="form-text">Use lowercase letters, numbers, and hyphens only</div>
                        </div>
                        
                        <div class="mb-3">
                            <label for="project_description" class="form-label">Description</label>
                            <input type="text" class="form-control" id="project_description" name="project_description" 
                                   placeholder="Brief description of your project">
                        </div>
                        
                        <div class="mb-4">
                            <label class="form-label">Project Type *</label>
                            <div class="row">
                                {% for type_key, type_info in project_types.items() %}
                                <div class="col-md-6 mb-3">
                                    <div class="card h-100">
                                        <div class="card-body text-center">
                                            <input type="radio" class="btn-check" name="project_type" 
                                                   id="{{ type_key }}" value="{{ type_key }}" 
                                                   {% if loop.first %}checked{% endif %}>
                                            <label class="btn btn-outline-{{ type_info.color }} w-100" for="{{ type_key }}">
                                                <div class="fs-2 mb-2">{{ type_info.icon }}</div>
                                                <h6 class="fw-bold">{{ type_info.name }}</h6>
                                                <p class="small mb-0">{{ type_info.description }}</p>
                                            </label>
                                        </div>
                                    </div>
                                </div>
                                {% endfor %}
                            </div>
                        </div>
                        
                        <div class="d-flex justify-content-between">
                            <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">
                                <i class="fas fa-arrow-left me-2"></i>Cancel
                            </a>
                            <button type="submit" class="btn btn-primary">
                                <i class="fas fa-plus me-2"></i>Create Project
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    return render_template_string(create_template, project_types=PROJECT_TYPES)

@app.route('/project/<project_name>')
def project_detail(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    # Simple project view
    simple_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ project_name }} - EchoNet Hosting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; }
        .card { border: 0; border-radius: 0.75rem; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05); }
        .btn { font-weight: 500; border-radius: 0.5rem; }
        .btn-primary { background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%); border: none; }
        .btn-success { background: linear-gradient(135deg, #198754 0%, #157347 100%); border: none; }
        .btn-danger { background: linear-gradient(135deg, #dc3545 0%, #bb2d3b 100%); border: none; }
        .breadcrumb { background: transparent; padding: 0; margin-bottom: 1rem; }
        .breadcrumb-item a { color: #0d6efd; text-decoration: none; }
        .alert { border-radius: 0.75rem; border: 0; font-weight: 500; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/dashboard">
                <i class="fas fa-server me-2"></i>EchoNet Hosting
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard">
                    <i class="fas fa-tachometer-alt me-1"></i>Dashboard
                </a>
                <a class="nav-link" href="/logout">
                    <i class="fas fa-sign-out-alt me-1"></i>Logout
                </a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
<div class="container py-4">
    <div class="row mb-4">
        <div class="col">
            <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                    <li class="breadcrumb-item">
                        <a href="{{ url_for('dashboard') }}">Dashboard</a>
                    </li>
                    <li class="breadcrumb-item active">{{ project_name }}</li>
                </ol>
            </nav>
            <h1 class="fw-bold mb-2">
                <i class="fas fa-folder text-primary me-2"></i>{{ project_name }}
            </h1>
        </div>
        <div class="col-auto">
            <div class="btn-group">
                {% if is_running %}
                    <a href="{{ url_for('stop_project', project_name=project_name) }}" class="btn btn-danger">
                        <i class="fas fa-stop me-2"></i>Stop
                    </a>
                    <a href="/app/{{ project_name }}" target="_blank" class="btn btn-outline-primary">
                        <i class="fas fa-external-link-alt me-2"></i>Open App
                    </a>
                {% else %}
                    <a href="{{ url_for('start_project', project_name=project_name) }}" class="btn btn-success">
                        <i class="fas fa-play me-2"></i>Start
                    </a>
                {% endif %}
                <a href="{{ url_for('console', project_name=project_name) }}" class="btn btn-warning">
                    <i class="fas fa-desktop me-2"></i>Console
                </a>
                <a href="{{ url_for('delete_project', project_name=project_name) }}" 
                   onclick="return confirm('Are you sure?')" class="btn btn-outline-danger">
                    <i class="fas fa-trash me-2"></i>Delete
                </a>
            </div>
        </div>
    </div>
    
    <div class="row">
        <div class="col-md-8">
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-file me-2"></i>Project Files</h5>
                    <div class="btn-group">
                        <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#uploadModal">
                            <i class="fas fa-upload me-1"></i>Upload
                        </button>
                        <button class="btn btn-success btn-sm" data-bs-toggle="modal" data-bs-target="#newFileModal">
                            <i class="fas fa-plus me-1"></i>New File
                        </button>
                        <button class="btn btn-info btn-sm" data-bs-toggle="modal" data-bs-target="#newFolderModal">
                            <i class="fas fa-folder-plus me-1"></i>New Folder
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Type</th>
                                    <th>Size</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for file in files %}
                                <tr>
                                    <td>
                                        <i class="fas fa-{{ 'folder' if file.is_dir else 'file' }} text-muted me-2"></i>
                                        <strong>{{ file.name }}</strong>
                                    </td>
                                    <td>{{ 'Folder' if file.is_dir else file.extension or 'File' }}</td>
                                    <td>{{ file.size if not file.is_dir else '-' }}</td>
                                    <td>
                                        <div class="btn-group btn-group-sm">
                                            {% if not file.is_dir %}
                                            <a href="/edit_file/{{ project_name }}/{{ file.name }}" class="btn btn-outline-primary btn-sm">
                                                <i class="fas fa-edit"></i>
                                            </a>
                                            <a href="/download_file/{{ project_name }}/{{ file.name }}" class="btn btn-outline-info btn-sm">
                                                <i class="fas fa-download"></i>
                                            </a>
                                            {% endif %}
                                            <button class="btn btn-outline-warning btn-sm" onclick="renameItem('{{ file.name }}')">
                                                <i class="fas fa-pencil-alt"></i>
                                            </button>
                                            <button class="btn btn-outline-danger btn-sm" onclick="deleteItem('{{ file.name }}')">
                                                <i class="fas fa-trash"></i>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                                {% endfor %}
                                {% if not files %}
                                <tr>
                                    <td colspan="4" class="text-center text-muted">No files found</td>
                                </tr>
                                {% endif %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Terminal Section -->
            <div class="card mt-3">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-terminal me-2"></i>Terminal</h5>
                    <button class="btn btn-outline-secondary btn-sm" onclick="clearTerminal()">
                        <i class="fas fa-eraser me-1"></i>Clear
                    </button>
                </div>
                <div class="card-body p-0">
                    <div class="terminal-container" style="height: 300px; background: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', monospace;">
                        <div id="terminal-output" style="height: 250px; overflow-y: auto; padding: 10px; font-size: 14px;"></div>
                        <div class="input-group" style="background: #2d2d2d; padding: 5px;">
                            <span class="input-group-text" style="background: #2d2d2d; color: #d4d4d4; border: none;">$</span>
                            <input type="text" id="terminal-input" class="form-control" 
                                   style="background: #2d2d2d; color: #d4d4d4; border: none; font-family: 'Consolas', monospace;"
                                   placeholder="Enter command..." onkeypress="handleTerminalInput(event)">
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <!-- Main File Management Card -->
            <div class="card mb-4">
                <div class="card-header">
                    <h6 class="mb-0"><i class="fas fa-play-circle text-success me-2"></i>Main File Settings</h6>
                </div>
                <div class="card-body">
                    <p class="text-muted small mb-3">Select which file will be executed when the project starts</p>
                    <form action="/set_main_file/{{ project_name }}" method="post">
                        <div class="mb-3">
                            <label for="main_file" class="form-label">Current Main File:</label>
                            <select class="form-select form-select-sm" id="main_file" name="main_file">
                                {% for py_file in python_files %}
                                <option value="{{ py_file }}" {% if py_file == current_main_file %}selected{% endif %}>
                                    {{ py_file }}
                                </option>
                                {% endfor %}
                                {% if not python_files %}
                                <option value="{{ current_main_file }}" selected>{{ current_main_file }}</option>
                                {% endif %}
                            </select>
                        </div>
                        <button type="submit" class="btn btn-primary btn-sm w-100">
                            <i class="fas fa-save me-1"></i>Update Main File
                        </button>
                    </form>
                    <div class="mt-3 p-2 bg-light rounded">
                        <small class="text-muted">
                            <i class="fas fa-info-circle me-1"></i>
                            Current: <strong>{{ current_main_file }}</strong>
                        </small>
                    </div>
                </div>
            </div>

            <!-- GitHub Sync Status -->
            <div class="card mb-4">
                <div class="card-header">
                    <h6 class="mb-0"><i class="fab fa-github text-dark me-2"></i>GitHub Sync</h6>
                </div>
                <div class="card-body">
                    {% if github_available %}
                    <div class="d-flex align-items-center">
                        <i class="fas fa-check-circle text-success me-2"></i>
                        <span class="text-success small">Connected & Syncing</span>
                    </div>
                    <small class="text-muted">All changes are automatically synced to GitHub</small>
                    {% else %}
                    <div class="d-flex align-items-center">
                        <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                        <span class="text-warning small">Offline Mode</span>
                    </div>
                    <small class="text-muted">Changes saved locally only</small>
                    {% endif %}
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-info-circle me-2"></i>Project Info</h5>
                </div>
                <div class="card-body">
                    <p><strong>Status:</strong> 
                        {% if is_running %}
                            <span class="badge bg-success">
                                <i class="fas fa-play me-1"></i>Running
                            </span>
                        {% else %}
                            <span class="badge bg-secondary">
                                <i class="fas fa-stop me-1"></i>Stopped
                            </span>
                        {% endif %}
                    </p>
                    {% if status.uptime and status.uptime > 0 %}
                    <p><strong>Uptime:</strong> 
                        <span class="badge bg-info">
                            <i class="fas fa-clock me-1"></i>{{ status.uptime|format_uptime }}
                        </span>
                    </p>
                    {% endif %}
                    {% if status.port %}
                    <p><strong>Port:</strong> {{ status.port }}</p>
                    {% endif %}
                    {% if status.memory_usage %}
                    <p><strong>Memory:</strong> {{ "%.2f"|format(status.memory_usage) }} MB</p>
                    {% endif %}
                    <p><strong>Project Size:</strong> 
                        {% if project_size %}
                            {{ project_size|format_file_size }}
                        {% else %}
                            Calculating...
                        {% endif %}
                    </p>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- File Upload Modal -->
<div class="modal fade" id="uploadModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Upload Files</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form action="/upload_file/{{ project_name }}" method="post" enctype="multipart/form-data">
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="files" class="form-label">Select files to upload:</label>
                        <input type="file" class="form-control" name="files" multiple required>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-primary">Upload</button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- New File Modal -->
<div class="modal fade" id="newFileModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Create New File</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form action="/create_file/{{ project_name }}" method="post">
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="filename" class="form-label">File name:</label>
                        <input type="text" class="form-control" name="filename" required>
                    </div>
                    <div class="mb-3">
                        <label for="content" class="form-label">Content:</label>
                        <textarea class="form-control" name="content" rows="5"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-success">Create</button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- New Folder Modal -->
<div class="modal fade" id="newFolderModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Create New Folder</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form action="/create_folder/{{ project_name }}" method="post">
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="foldername" class="form-label">Folder name:</label>
                        <input type="text" class="form-control" name="foldername" required>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-info">Create</button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
function renameItem(filename) {
    const newName = prompt('Enter new name:', filename);
    if (newName && newName !== filename) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/rename_item/{{ project_name }}';
        
        const oldNameInput = document.createElement('input');
        oldNameInput.type = 'hidden';
        oldNameInput.name = 'old_name';
        oldNameInput.value = filename;
        form.appendChild(oldNameInput);
        
        const newNameInput = document.createElement('input');
        newNameInput.type = 'hidden';
        newNameInput.name = 'new_name';
        newNameInput.value = newName;
        form.appendChild(newNameInput);
        
        document.body.appendChild(form);
        form.submit();
    }
}

function deleteItem(filename) {
    if (confirm('Are you sure you want to delete "' + filename + '"?')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/delete_item/{{ project_name }}';
        
        const filenameInput = document.createElement('input');
        filenameInput.type = 'hidden';
        filenameInput.name = 'filename';
        filenameInput.value = filename;
        form.appendChild(filenameInput);
        
        document.body.appendChild(form);
        form.submit();
    }
}

function clearTerminal() {
    document.getElementById('terminal-output').innerHTML = '';
}

function handleTerminalInput(event) {
    if (event.key === 'Enter') {
        const input = event.target;
        const command = input.value.trim();
        if (command) {
            addToTerminal('$ ' + command);
            executeCommand(command);
            input.value = '';
        }
    }
}

function addToTerminal(text) {
    const output = document.getElementById('terminal-output');
    const div = document.createElement('div');
    div.textContent = text;
    output.appendChild(div);
    output.scrollTop = output.scrollHeight;
}

function executeCommand(command) {
    fetch('/execute_command/{{ project_name }}', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({command: command})
    })
    .then(response => response.json())
    .then(data => {
        if (data.output) {
            addToTerminal(data.output);
        }
        if (data.error) {
            addToTerminal('Error: ' + data.error);
        }
    })
    .catch(error => {
        addToTerminal('Error: ' + error.message);
    });
}
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    # Get project files with detailed info
    files = []
    try:
        for item in os.listdir(project_path):
            item_path = os.path.join(project_path, item)
            is_dir = os.path.isdir(item_path)
            
            # Get file size
            size = "-"
            extension = ""
            if not is_dir:
                try:
                    size_bytes = os.path.getsize(item_path)
                    size = f"{size_bytes:,} bytes" if size_bytes < 1024 else f"{size_bytes/1024:.1f} KB"
                    extension = os.path.splitext(item)[1].lstrip('.')
                except:
                    size = "-"
            
            files.append({
                'name': item,
                'is_dir': is_dir,
                'size': size,
                'extension': extension
            })
        
        # Sort: directories first, then files alphabetically
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    except Exception as e:
        logging.error(f"Error listing project files: {e}")
    
    is_running = process_manager.is_project_running(project_name)
    status = process_manager.get_project_status(project_name)
    
    # Calculate project size
    project_size = calculate_project_size(project_path)
    
    # Get current main file from config
    current_main_file = "main.py"  # default
    try:
        config_path = os.path.join(project_path, 'echonet.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            if 'runtime' in config and 'main_file' in config['runtime']:
                current_main_file = config['runtime']['main_file']
            elif 'main_file' in config:
                current_main_file = config['main_file']
    except Exception as e:
        logging.warning(f"Could not read main file from config: {e}")
    
    # Get available Python files for main file selection
    python_files = [f['name'] for f in files if not f['is_dir'] and f['name'].endswith('.py')]
    
    return render_template_string(simple_template, 
                                project_name=project_name, 
                                files=files, 
                                is_running=is_running, 
                                status=status,
                                project_size=project_size,
                                current_main_file=current_main_file,
                                python_files=python_files,
                                github_available=github_manager.is_available())

@app.route('/set_main_file/<project_name>', methods=['POST'])
def set_main_file(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    new_main_file = request.form.get('main_file', '').strip()
    if not new_main_file:
        flash('Main file cannot be empty!', 'danger')
        return redirect(url_for('project_detail', project_name=project_name))
    
    # Check if the file exists
    main_file_path = os.path.join(project_path, new_main_file)
    if not os.path.exists(main_file_path):
        flash(f'File "{new_main_file}" does not exist!', 'danger')
        return redirect(url_for('project_detail', project_name=project_name))
    
    try:
        # Update using GitHub manager which handles both local and remote
        if github_manager.update_project_main_file(project_name, new_main_file):
            if github_manager.is_available():
                flash(f'Main file set to "{new_main_file}" and synced to GitHub!', 'success')
            else:
                flash(f'Main file set to "{new_main_file}" locally (GitHub not available)!', 'info')
        else:
            flash('Error updating main file!', 'danger')
    except Exception as e:
        flash(f'Error setting main file: {str(e)}', 'danger')
        logging.error(f'Error setting main file for {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/console/<project_name>')
def console(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    project_status = process_manager.get_project_status(project_name)
    logs = process_manager.get_project_logs(project_name)
    
    console_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Console - {{ project_name }} - EchoNet Hosting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; }
        .card { border: 0; border-radius: 0.75rem; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05); }
        .btn { font-weight: 500; border-radius: 0.5rem; }
        .btn-primary { background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%); border: none; }
        .btn-outline-info:hover { background: #0dcaf0; border-color: #0dcaf0; }
        .btn-outline-secondary:hover { background: #6c757d; border-color: #6c757d; }
        .breadcrumb { background: transparent; padding: 0; margin-bottom: 1rem; }
        .breadcrumb-item a { color: #0d6efd; text-decoration: none; }
        .alert { border-radius: 0.75rem; border: 0; font-weight: 500; }
        .console-output {
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.4;
            height: 500px;
            overflow-y: auto;
            border-radius: 0 0 0.375rem 0.375rem;
        }
        .console-text {
            margin: 0;
            padding: 0;
            background: transparent;
            border: none;
            color: inherit;
            font-family: inherit;
            font-size: inherit;
            line-height: inherit;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        @media (max-width: 768px) {
            .console-output { height: 400px; font-size: 12px; }
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/dashboard">
                <i class="fas fa-server me-2"></i>EchoNet Hosting
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard">
                    <i class="fas fa-tachometer-alt me-1"></i>Dashboard
                </a>
                <a class="nav-link" href="/logout">
                    <i class="fas fa-sign-out-alt me-1"></i>Logout
                </a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
<div class="container py-4">
    <div class="row mb-4">
        <div class="col">
            <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                    <li class="breadcrumb-item">
                        <a href="{{ url_for('dashboard') }}">Dashboard</a>
                    </li>
                    <li class="breadcrumb-item">
                        <a href="{{ url_for('project_detail', project_name=project_name) }}">{{ project_name }}</a>
                    </li>
                    <li class="breadcrumb-item active">Console</li>
                </ol>
            </nav>
            <h1 class="fw-bold mb-2">
                <i class="fas fa-desktop text-warning me-2"></i>Console - {{ project_name }}
            </h1>
        </div>
        <div class="col-auto">
            <div class="btn-group">
                <button class="btn btn-outline-info" onclick="refreshLogs()">
                    <i class="fas fa-sync-alt me-2"></i>Refresh
                </button>
                <a href="{{ url_for('project_detail', project_name=project_name) }}" class="btn btn-outline-secondary">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
        </div>
    </div>
    
    <div class="row">
        <div class="col">
            <div class="card">
                <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                    <h5 class="mb-0 fw-bold">
                        <i class="fas fa-terminal me-2"></i>Console Output
                    </h5>
                    <div class="d-flex align-items-center">
                        <div class="form-check form-switch me-3">
                            <input class="form-check-input" type="checkbox" id="autoRefresh" checked>
                            <label class="form-check-label text-white" for="autoRefresh">Auto-refresh</label>
                        </div>
                        <small class="text-muted">Status: 
                            {% if project_status.status == 'running' %}
                                <span class="text-success">Running</span>
                            {% else %}
                                <span class="text-secondary">Stopped</span>
                            {% endif %}
                        </small>
                    </div>
                </div>
                <div class="card-body p-0">
                    <div id="consoleOutput" class="console-output p-3">
                        {% if logs %}
                            <pre class="console-text">{{ logs }}</pre>
                        {% else %}
                            <div class="text-center py-5">
                                <i class="fas fa-file-alt fa-3x text-muted mb-3"></i>
                                <h5 class="text-muted">No logs available</h5>
                                <p class="text-muted">
                                    {% if project_status.status == 'running' %}
                                        Your project is running but hasn't generated logs yet.
                                    {% else %}
                                        Start your project to see logs here.
                                    {% endif %}
                                </p>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
let autoRefreshInterval;

document.addEventListener('DOMContentLoaded', function() {
    const autoRefreshCheckbox = document.getElementById('autoRefresh');
    if (autoRefreshCheckbox.checked) {
        startAutoRefresh();
    }
    
    autoRefreshCheckbox.addEventListener('change', function() {
        if (this.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });
});

function startAutoRefresh() {
    autoRefreshInterval = setInterval(refreshLogs, 3000);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

function refreshLogs() {
    fetch(`/api/get_logs/{{ project_name }}`)
        .then(response => response.json())
        .then(data => {
            if (data.logs !== undefined) {
                updateConsoleOutput(data.logs);
            }
        })
        .catch(error => {
            console.error('Error refreshing logs:', error);
        });
}

function updateConsoleOutput(logs) {
    const consoleOutput = document.getElementById('consoleOutput');
    
    if (logs && logs.trim()) {
        // Remove timestamps for cleaner output
        let cleanedLogs = logs
            .replace(/^\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}[^\\]]*\\]\\s*/gm, '')
            .replace(/^\\[\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}[^\\]]*\\]\\s*/gm, '')
            .replace(/^\\d{2}:\\d{2}:\\d{2}\\s+/gm, '');
        
        consoleOutput.innerHTML = `<pre class="console-text">${cleanedLogs}</pre>`;
    } else {
        consoleOutput.innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-file-alt fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">No logs available</h5>
                <p class="text-muted">Your project hasn't generated logs yet.</p>
            </div>
        `;
    }
    
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    return render_template_string(console_template, 
                                project_name=project_name, 
                                project_status=project_status, 
                                logs=logs)

@app.route('/start_project/<project_name>')
def start_project(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    if process_manager.start_project(project_name):
        flash(f'Project "{project_name}" started successfully!', 'success')
    else:
        flash(f'Failed to start project "{project_name}"', 'danger')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/stop_project/<project_name>')
def stop_project(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    if process_manager.stop_project(project_name):
        flash(f'Project "{project_name}" stopped successfully!', 'success')
    else:
        flash(f'Failed to stop project "{project_name}"', 'danger')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/delete_project/<project_name>')
def delete_project(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Stop project if running
        if process_manager.is_project_running(project_name):
            process_manager.stop_project(project_name)
        
        # Delete from GitHub first
        if github_manager.is_available():
            try:
                github_manager.delete_project_from_github(project_name)
                logging.info(f"Deleted project {project_name} from GitHub")
            except Exception as e:
                logging.error(f"Error deleting project from GitHub: {e}")
                # Continue with local deletion even if GitHub deletion fails
        
        # Delete project directory
        shutil.rmtree(project_path)
        flash(f'Project "{project_name}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting project: {str(e)}', 'danger')
        logging.error(f'Error deleting project {project_name}: {e}')
    
    return redirect(url_for('dashboard'))

# =============================================================================
# FILE MANAGEMENT ROUTES
# =============================================================================

@app.route('/upload_file/<project_name>', methods=['POST'])
def upload_file(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        if 'files' not in request.files:
            flash('No files selected!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        files = request.files.getlist('files')
        uploaded_count = 0
        
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                if filename:
                    file_path = os.path.join(project_path, filename)
                    file.save(file_path)
                    uploaded_count += 1
                    
                    # Sync each uploaded file to GitHub
                    if github_manager.is_available():
                        github_manager.sync_file_to_github(project_name, filename)
        
        if uploaded_count > 0:
            if github_manager.is_available():
                flash(f'Successfully uploaded {uploaded_count} file(s) and synced to GitHub!', 'success')
            else:
                flash(f'Successfully uploaded {uploaded_count} file(s) locally (GitHub not available)!', 'info')
        else:
            flash('No valid files to upload!', 'warning')
    
    except Exception as e:
        flash(f'Error uploading files: {str(e)}', 'danger')
        logging.error(f'Error uploading files to {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/create_file/<project_name>', methods=['POST'])
def create_file(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        filename = secure_filename(request.form.get('filename', '').strip())
        content = request.form.get('content', '')
        
        if not filename:
            flash('Please provide a valid filename!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        file_path = os.path.join(project_path, filename)
        if os.path.exists(file_path):
            flash('File already exists!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        flash(f'File "{filename}" created successfully!', 'success')
    
    except Exception as e:
        flash(f'Error creating file: {str(e)}', 'danger')
        logging.error(f'Error creating file in {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/create_folder/<project_name>', methods=['POST'])
def create_folder(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        foldername = secure_filename(request.form.get('foldername', '').strip())
        
        if not foldername:
            flash('Please provide a valid folder name!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        folder_path = os.path.join(project_path, foldername)
        if os.path.exists(folder_path):
            flash('Folder already exists!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        os.makedirs(folder_path)
        flash(f'Folder "{foldername}" created successfully!', 'success')
    
    except Exception as e:
        flash(f'Error creating folder: {str(e)}', 'danger')
        logging.error(f'Error creating folder in {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/rename_item/<project_name>', methods=['POST'])
def rename_item(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        old_name = request.form.get('old_name', '').strip()
        new_name = secure_filename(request.form.get('new_name', '').strip())
        
        if not old_name or not new_name:
            flash('Please provide valid names!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        old_path = os.path.join(project_path, old_name)
        new_path = os.path.join(project_path, new_name)
        
        if not os.path.exists(old_path):
            flash('Item not found!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        if os.path.exists(new_path):
            flash('Target name already exists!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        os.rename(old_path, new_path)
        flash(f'Successfully renamed "{old_name}" to "{new_name}"!', 'success')
    
    except Exception as e:
        flash(f'Error renaming item: {str(e)}', 'danger')
        logging.error(f'Error renaming item in {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/delete_item/<project_name>', methods=['POST'])
def delete_item(project_name):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        filename = request.form.get('filename', '').strip()
        
        if not filename:
            flash('Please specify an item to delete!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        item_path = os.path.join(project_path, filename)
        
        if not os.path.exists(item_path):
            flash('Item not found!', 'warning')
            return redirect(url_for('project_detail', project_name=project_name))
        
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
            flash(f'Folder "{filename}" deleted successfully!', 'success')
        else:
            os.remove(item_path)
            flash(f'File "{filename}" deleted successfully!', 'success')
    
    except Exception as e:
        flash(f'Error deleting item: {str(e)}', 'danger')
        logging.error(f'Error deleting item in {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/edit_file/<project_name>/<filename>')
def edit_file(project_name, filename):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    file_path = os.path.join(project_path, filename)
    
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        flash('File not found!', 'danger')
        return redirect(url_for('project_detail', project_name=project_name))
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash(f'Error reading file: {str(e)}', 'danger')
        return redirect(url_for('project_detail', project_name=project_name))
    
    edit_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit {{ filename }} - {{ project_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .editor-container { height: 70vh; }
        textarea { font-family: 'Consolas', 'Monaco', 'Courier New', monospace; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/dashboard">
                <i class="fas fa-server me-2"></i>EchoNet Hosting
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/project/{{ project_name }}">
                    <i class="fas fa-arrow-left me-1"></i>Back to Project
                </a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-4">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0"><i class="fas fa-edit me-2"></i>Edit {{ filename }}</h5>
            </div>
            <div class="card-body">
                <form action="/save_file/{{ project_name }}/{{ filename }}" method="post">
                    <div class="mb-3">
                        <textarea name="content" class="form-control editor-container" required>{{ content }}</textarea>
                    </div>
                    <div class="d-flex justify-content-between">
                        <a href="/project/{{ project_name }}" class="btn btn-secondary">
                            <i class="fas fa-times me-1"></i>Cancel
                        </a>
                        <button type="submit" class="btn btn-success">
                            <i class="fas fa-save me-1"></i>Save Changes
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    return render_template_string(edit_template, 
                                project_name=project_name, 
                                filename=filename, 
                                content=content)

@app.route('/save_file/<project_name>/<filename>', methods=['POST'])
def save_file(project_name, filename):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    file_path = os.path.join(project_path, filename)
    
    try:
        content = request.form.get('content', '')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Sync file to GitHub
        if github_manager.is_available():
            if github_manager.sync_file_to_github(project_name, filename):
                flash(f'File "{filename}" saved and synced to GitHub successfully!', 'success')
            else:
                flash(f'File "{filename}" saved locally but GitHub sync failed!', 'warning')
        else:
            flash(f'File "{filename}" saved locally (GitHub not available)!', 'info')
    
    except Exception as e:
        flash(f'Error saving file: {str(e)}', 'danger')
        logging.error(f'Error saving file {filename} in {project_name}: {e}')
    
    return redirect(url_for('project_detail', project_name=project_name))

@app.route('/download_file/<project_name>/<filename>')
def download_file(project_name, filename):
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    file_path = os.path.join(project_path, filename)
    
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        flash('File not found!', 'danger')
        return redirect(url_for('project_detail', project_name=project_name))
    
    try:
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'danger')
        return redirect(url_for('project_detail', project_name=project_name))

@app.route('/execute_command/<project_name>', methods=['POST'])
def execute_command(project_name):
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({'error': 'No command provided'}), 400
        
        # Determine shell and modify command for Termux compatibility
        is_termux = os.path.exists('/data/data/com.termux')
        
        # For Termux, ensure proper PATH and shell
        if is_termux:
            # Use bash explicitly and source Termux environment
            shell_command = f"bash -c 'source $PREFIX/etc/bash.bashrc 2>/dev/null; export PATH=$PREFIX/bin:$PATH; {command}'"
        else:
            shell_command = command
        
        # Determine timeout based on command type
        timeout_seconds = 30  # default
        if any(cmd in command.lower() for cmd in ['pip install', 'npm install', 'apt install', 'pkg install']):
            timeout_seconds = 300  # 5 minutes for package installations
        elif any(cmd in command.lower() for cmd in ['git clone', 'wget', 'curl']):
            timeout_seconds = 120  # 2 minutes for downloads
        
        # Execute command in project directory
        result = subprocess.run(
            shell_command,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        
        output = result.stdout
        if result.stderr:
            output += '\n' + result.stderr
        
        return jsonify({
            'output': output,
            'return_code': result.returncode
        })
    
    except subprocess.TimeoutExpired:
        timeout_msg = f'Command timeout ({timeout_seconds}s limit)'
        if timeout_seconds > 30:
            timeout_msg += ' - This is normal for package installations'
        return jsonify({'error': timeout_msg})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/start_all_projects')
def start_all_projects():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    try:
        stats = get_project_stats()
        started_count = 0
        failed_count = 0
        
        for project in stats['projects']:
            if project['status'] == 'stopped':
                if process_manager.start_project(project['name']):
                    started_count += 1
                else:
                    failed_count += 1
        
        if started_count > 0:
            flash(f'Started {started_count} projects successfully!', 'success')
        if failed_count > 0:
            flash(f'Failed to start {failed_count} projects', 'warning')
        
    except Exception as e:
        flash(f'Error starting projects: {str(e)}', 'danger')
        logging.error(f'Error in start_all_projects: {e}')
    
    return redirect(url_for('dashboard'))

@app.route('/stop_all_projects')
def stop_all_projects():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    try:
        stats = get_project_stats()
        stopped_count = 0
        failed_count = 0
        
        for project in stats['projects']:
            if project['status'] == 'running':
                if process_manager.stop_project(project['name']):
                    stopped_count += 1
                else:
                    failed_count += 1
        
        if stopped_count > 0:
            flash(f'Stopped {stopped_count} projects successfully!', 'success')
        if failed_count > 0:
            flash(f'Failed to stop {failed_count} projects', 'warning')
            
    except Exception as e:
        flash(f'Error stopping projects: {str(e)}', 'danger')
        logging.error(f'Error in stop_all_projects: {e}')
    
    return redirect(url_for('dashboard'))

@app.route('/restart_all_projects')
def restart_all_projects():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    try:
        stats = get_project_stats()
        restarted_count = 0
        failed_count = 0
        
        # First stop all running projects
        for project in stats['projects']:
            if project['status'] == 'running':
                process_manager.stop_project(project['name'])
        
        # Give a brief moment for processes to stop
        time.sleep(1)
        
        # Then start all projects
        for project in stats['projects']:
            if process_manager.start_project(project['name']):
                restarted_count += 1
            else:
                failed_count += 1
        
        if restarted_count > 0:
            flash(f'Restarted {restarted_count} projects successfully!', 'success')
        if failed_count > 0:
            flash(f'Failed to restart {failed_count} projects', 'warning')
            
    except Exception as e:
        flash(f'Error restarting projects: {str(e)}', 'danger')
        logging.error(f'Error in restart_all_projects: {e}')
    
    return redirect(url_for('dashboard'))

@app.route('/import_project', methods=['POST'])
def import_project():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    
    if not resource_manager.enforce_limits():
        flash('Cannot import project: Resource limits exceeded', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        if 'zip_file' not in request.files:
            flash('No ZIP file provided', 'danger')
            return redirect(url_for('dashboard'))
        
        zip_file = request.files['zip_file']
        if zip_file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('dashboard'))
        
        if not zip_file.filename.endswith('.zip'):
            flash('Please upload a ZIP file', 'danger')
            return redirect(url_for('dashboard'))
        
        # Generate project name from filename (preserve case)
        project_name = secure_filename(zip_file.filename.replace('.zip', '').replace(' ', '-'))
        if not project_name:
            flash('Invalid ZIP filename', 'danger')
            return redirect(url_for('dashboard'))
        
        project_path = os.path.join(PROJECTS_DIR, project_name)
        
        # Check if project already exists
        if os.path.exists(project_path):
            flash(f'Project "{project_name}" already exists!', 'warning')
            return redirect(url_for('dashboard'))
        
        # Save and extract ZIP file
        temp_zip_path = f"/tmp/{project_name}.zip"
        zip_file.save(temp_zip_path)
        
        # Extract ZIP
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            os.makedirs(project_path, exist_ok=True)
            zip_ref.extractall(project_path)
        
        # Clean up temp file
        os.remove(temp_zip_path)
        
        # Create basic project metadata if not exists
        metadata_path = os.path.join(project_path, 'echonet.json')
        if not os.path.exists(metadata_path):
            metadata = {
                'name': project_name,
                'type': 'python_script',
                'created': datetime.now().isoformat(),
                'imported': True,
                'main_file': 'main.py',
                'version': '1.0.0'
            }
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
        
        flash(f'Project "{project_name}" imported successfully!', 'success')
        return redirect(url_for('project_detail', project_name=project_name))
        
    except Exception as e:
        flash(f'Error importing project: {str(e)}', 'danger')
        logging.error(f'Error importing project: {e}')
        return redirect(url_for('dashboard'))

@app.route('/api/get_logs/<project_name>')
def get_logs(project_name):
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        # Get logs with improved persistence
        logs = process_manager.get_project_logs(project_name)
        status = process_manager.get_project_status(project_name)
        
        # If no logs found and project is running, create a new log file
        if not logs and status.get('status') == 'running':
            main_log = os.path.join(PROJECTS_DIR, project_name, 'app.log')
            try:
                os.makedirs(os.path.dirname(main_log), exist_ok=True)
                with open(main_log, 'w', encoding='utf-8') as f:
                    f.write(f'Log file recreated at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\\n')
                    f.write(f'Project {project_name} is running...\\n')
                logs = f'Log file recreated - monitoring {project_name}...\\n'
            except Exception as create_error:
                logging.warning(f'Could not create log file: {create_error}')
                logs = 'Console monitoring active - logs will appear here...\\n'
        
        return jsonify({
            'logs': logs,
            'status': status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Proxy route for running applications
@app.route('/app/<project_name>')
@app.route('/app/<project_name>/<path:path>')
def proxy_app(project_name, path=''):
    """Proxy requests to running project applications"""
    if not process_manager.is_project_running(project_name):
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Service Unavailable</title>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    border-radius: 12px;
                    padding: 40px;
                    max-width: 500px;
                    width: 100%;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                .icon {{
                    color: #ff6b6b;
                    font-size: 4rem;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #333;
                    margin: 0 0 16px 0;
                    font-size: 1.5rem;
                    font-weight: 600;
                }}
                p {{
                    color: #666;
                    line-height: 1.6;
                    margin: 0 0 12px 0;
                }}
                .developer-note {{
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 6px;
                    padding: 12px;
                    margin-top: 20px;
                    font-size: 0.9rem;
                    color: #6c757d;
                }}
                @media (max-width: 768px) {{
                    body {{ padding: 15px; }}
                    .container {{ padding: 30px 20px; }}
                    .icon {{ font-size: 3rem; }}
                    h1 {{ font-size: 1.3rem; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <i class="fas fa-exclamation-triangle icon"></i>
                <h1>Service Temporarily Unavailable</h1>
                <p>The requested service is currently not running.</p>
                <p>Please try again later or contact the service administrator.</p>
                <div class="developer-note">
                    <i class="fas fa-info-circle" style="margin-right: 8px;"></i>
                    If you're the developer, check your application console for more details.
                </div>
            </div>
        </body>
        </html>
        """, 503
    
    try:
        # Get the project's port
        status = process_manager.get_project_status(project_name)
        port = status.get('port')
        
        if not port:
            raise Exception("No port assigned")
        
        # Simple proxy - redirect to the internal port
        import requests
        target_url = f"http://127.0.0.1:{port}/{path}"
        
        # Forward the request
        response = requests.get(target_url, 
                              params=request.args,
                              headers={'Host': request.host},
                              timeout=10)
        
        # Return the response
        return response.content, response.status_code, dict(response.headers)
        
    except Exception as e:
        logging.error(f"Error proxying to project {project_name}: {e}")
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Connection Error</title>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    border-radius: 12px;
                    padding: 40px;
                    max-width: 500px;
                    width: 100%;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                .icon {{
                    color: #ffc107;
                    font-size: 4rem;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #333;
                    margin: 0 0 16px 0;
                    font-size: 1.5rem;
                    font-weight: 600;
                }}
                p {{
                    color: #666;
                    line-height: 1.6;
                    margin: 0 0 12px 0;
                }}
                .error-details {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    border-radius: 6px;
                    padding: 12px;
                    margin: 16px 0;
                    font-size: 0.9rem;
                    color: #856404;
                    word-break: break-all;
                }}
                .developer-note {{
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 6px;
                    padding: 12px;
                    margin-top: 20px;
                    font-size: 0.9rem;
                    color: #6c757d;
                }}
                @media (max-width: 768px) {{
                    body {{ padding: 15px; }}
                    .container {{ padding: 30px 20px; }}
                    .icon {{ font-size: 3rem; }}
                    h1 {{ font-size: 1.3rem; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <i class="fas fa-wifi icon"></i>
                <h1>Connection Error</h1>
                <p>Unable to establish connection to the requested service.</p>
                <p>The service might be starting up or experiencing technical difficulties.</p>
                <div class="error-details">
                    <strong>Technical Details:</strong><br>
                    {str(e)}
                </div>
                <div class="developer-note">
                    <i class="fas fa-info-circle" style="margin-right: 8px;"></i>
                    If you're the developer, check your application console and server logs for more information.
                </div>
            </div>
        </body>
        </html>
        """, 502

# =============================================================================
# APPLICATION STARTUP
# =============================================================================

def restore_running_projects():
    """Restore previously running projects on startup"""
    try:
        logging.info("Restoring previously running projects...")
        for project_name in list(process_manager.processes.keys()):
            if not process_manager.is_project_running(project_name):
                logging.info(f"Restarting project: {project_name}")
                process_manager.start_project(project_name)
    except Exception as e:
        logging.error(f"Error restoring running projects: {e}")

# Initialize app with delayed restoration
def init_app():
    def delayed_restore():
        time.sleep(5)  # Wait 5 seconds for system to stabilize
        restore_running_projects()
    
    thread = threading.Thread(target=delayed_restore)
    thread.daemon = True
    thread.start()

init_app()

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == '__main__':
    # Production-ready configuration
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)