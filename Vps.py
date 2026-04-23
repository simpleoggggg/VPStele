import os
import re
import asyncio
import subprocess
import signal
import logging
import json
import shlex
import threading
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BASE_WORKSPACES_DIR = os.path.abspath("workspaces")
PROCESSES_FILE = "processes.json"
MAX_OUTPUT_LENGTH = 4000

user_sessions = {}
running_processes = {}

ALLOWED_COMMANDS = [
    'ls', 'cat', 'head', 'tail', 'grep', 'find', 'wc', 'sort', 'uniq',
    'echo', 'pwd', 'mkdir', 'touch', 'cp', 'mv', 'rm', 'rmdir',
    'clear', 'date', 'whoami', 'file', 'diff', 'basename', 'dirname',
    'stat', 'du', 'tar', 'unzip', 'zip', 'gzip', 'gunzip', 'chmod',
    'git', 'curl', 'wget', 'pip', 'pip3', 'npm', 'npx', 'node',
    'python', 'python3', 'nohup', 'screen', 'nano', 'vim', 'vi',
    'less', 'more', 'awk', 'sed', 'cut', 'tr', 'tee', 'xargs',
    'ln', 'readlink', 'realpath', 'which', 'whereis', 'type',
    'env', 'export', 'set', 'unset', 'printenv',
    'df', 'free', 'top', 'htop', 'ps', 'kill', 'killall', 'pkill',
    'uptime', 'uname', 'hostname', 'id', 'groups', 'users',
    'history', 'alias', 'unalias', 'source', 'exec',
    'sleep', 'time', 'timeout', 'watch', 'cron', 'crontab', 'at',
    'ssh', 'scp', 'rsync', 'sftp', 'ftp', 'telnet', 'netstat', 'ss',
    'ping', 'traceroute', 'nslookup', 'dig', 'host', 'ifconfig', 'ip',
    'iptables', 'route', 'arp', 'netcat', 'nc', 'nmap',
    'apt', 'apt-get', 'yum', 'dnf', 'pacman', 'brew', 'snap',
    'dpkg', 'rpm', 'make', 'cmake', 'gcc', 'g++', 'clang',
    'java', 'javac', 'mvn', 'gradle', 'ant',
    'ruby', 'gem', 'bundle', 'rake', 'rails',
    'php', 'composer', 'artisan', 'laravel',
    'go', 'cargo', 'rustc', 'rustup',
    'perl', 'lua', 'swift', 'kotlin', 'scala',
    'docker', 'docker-compose', 'kubectl', 'helm', 'minikube',
    'systemctl', 'service', 'journalctl', 'dmesg',
    'chown', 'chgrp', 'umask', 'getfacl', 'setfacl',
    'cmp', 'comm', 'patch', 'strings', 'od', 'hexdump', 'xxd',
    'base64', 'md5sum', 'sha256sum', 'sha512sum', 'openssl',
    'ssh-keygen', 'ssh-copy-id', 'ssh-add', 'ssh-agent',
    'gpg', 'gpg2', 'pass',
    'jq', 'yq', 'xmllint', 'csvtool',
    'ffmpeg', 'convert', 'identify', 'mogrify',
    'pandoc', 'latex', 'pdflatex', 'xelatex',
    'sqlite3', 'mysql', 'psql', 'mongo', 'redis-cli',
    'screen', 'tmux', 'byobu', 'nohup', 'disown', 'bg', 'fg', 'jobs',
    'lsof', 'strace', 'ltrace', 'gdb', 'valgrind',
    'mount', 'umount', 'fdisk', 'parted', 'mkfs', 'fsck',
    'dd', 'sync', 'shred', 'wipe',
    'useradd', 'usermod', 'userdel', 'groupadd', 'groupmod', 'groupdel',
    'passwd', 'chpasswd', 'su', 'sudo',
    'crontab', 'at', 'batch', 'anacron',
    'logrotate', 'logger', 'syslog',
    'man', 'info', 'help', 'apropos', 'whatis',
    'cal', 'bc', 'dc', 'expr', 'factor', 'seq', 'shuf',
    'rev', 'tac', 'nl', 'fmt', 'fold', 'column', 'colrm', 'expand', 'unexpand',
    'split', 'csplit', 'paste', 'join', 'pr',
    'test', 'true', 'false', 'yes', 'no',
    'iconv', 'recode', 'convmv',
    'tree', 'ncdu', 'ranger', 'mc',
    'htpasswd', 'ab', 'siege', 'wrk',
    'certbot', 'letsencrypt',
    'yarn', 'pnpm', 'bun', 'deno',
    'ts-node', 'tsx', 'esbuild', 'webpack', 'vite', 'rollup', 'parcel',
    'pytest', 'unittest', 'nose', 'tox', 'coverage',
    'jest', 'mocha', 'chai', 'cypress', 'playwright',
    'eslint', 'prettier', 'black', 'flake8', 'pylint', 'mypy',
    'virtualenv', 'venv', 'pipenv', 'poetry', 'conda',
    'aws', 'gcloud', 'az', 'heroku', 'vercel', 'netlify', 'fly',
    'terraform', 'ansible', 'puppet', 'chef', 'vagrant',
]

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Telegram Bot Manager is Running 24/7! (Keep-Alive Active)"

@flask_app.route('/health')
def health():
    return {"status": "healthy", "bot": "running"}

def run_web_server():
    try:
        port = int(os.environ.get('PORT', 8000))
        print(f"Flask Web Server running on 0.0.0.0:{port}...")
        flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Flask Web Server Error: {e}")

def start_keep_alive():
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()


def ensure_workspace(user_id: int) -> str:
    workspace_path = os.path.join(BASE_WORKSPACES_DIR, str(user_id))
    os.makedirs(workspace_path, exist_ok=True)
    return os.path.abspath(workspace_path)


def get_user_cwd(user_id: int) -> str:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "cwd": ensure_workspace(user_id),
        }
    return user_sessions[user_id]["cwd"]


def set_user_cwd(user_id: int, new_cwd: str) -> bool:
    workspace = ensure_workspace(user_id)
    abs_path = os.path.abspath(new_cwd)
    
    if not abs_path.startswith(workspace):
        return False
    
    if os.path.isdir(abs_path):
        user_sessions[user_id]["cwd"] = abs_path
        return True
    return False


def is_path_in_workspace(path: str, workspace: str, cwd: str) -> bool:
    if path.startswith('/'):
        resolved = os.path.abspath(os.path.join(workspace, path.lstrip('/')))
    else:
        resolved = os.path.abspath(os.path.join(cwd, path))
    return resolved.startswith(workspace)


def check_command_safety(command: str, workspace: str, cwd: str) -> tuple:
    dangerous_patterns = [
        r'/etc/', r'/var/', r'/usr/', r'/bin/', r'/sbin/',
        r'/root', r'/home/runner(?!/workspace)', r'/proc/', r'/sys/', r'/dev/',
        r'\$\(', r'`.*`',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False, "Access to system directories not allowed."
    
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    
    if not parts:
        return False, "No command provided"
    
    base_cmd = parts[0]
    
    if base_cmd not in ALLOWED_COMMANDS:
        if not base_cmd.endswith('.py') and not base_cmd.endswith('.sh') and not base_cmd.endswith('.js'):
            return False, f"Command `{base_cmd}` not allowed.\n\nUse /commands to see allowed commands."
    
    for arg in parts[1:]:
        if arg.startswith('-'):
            continue
        if '..' in arg:
            test_path = os.path.normpath(os.path.join(cwd, arg))
            if not test_path.startswith(workspace):
                return False, "Cannot access paths outside workspace."
    
    return True, ""


def load_processes():
    global running_processes
    if os.path.exists(PROCESSES_FILE):
        try:
            with open(PROCESSES_FILE, 'r') as f:
                running_processes = json.load(f)
        except:
            running_processes = {}


def save_processes():
    with open(PROCESSES_FILE, 'w') as f:
        json.dump(running_processes, f, indent=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    workspace = ensure_workspace(user_id)
    
    welcome_msg = """**VPS Bot - Full Terminal Access**

Welcome! You now have your own VPS environment with 200+ commands.

**Terminal Commands:**
- Just type commands directly (ls, cd, mkdir, git, etc.)
- `cd <dir>` - Change directory
- `git clone <url>` - Clone repositories
- `pip install <pkg>` - Install Python packages
- `python3 script.py` - Run Python scripts

**File Operations:**
- `/upload` - Upload files
- `/download <file>` - Download files

**24/7 Bot Hosting:**
- `/run python3 bot.py` - Run a process 24/7
- `/stop <id>` - Stop a process
- `/ps` - List processes
- `/logs <id>` - View logs

**System Info:**
- `/sysinfo` - Show system information
- `/disk` - Show disk usage
- `/memory` - Show memory usage

**Other:**
- `/help` - Show this message
- `/myid` - Get your user ID
- `/commands` - List all allowed commands

Start typing commands!"""

    await update.message.reply_text(welcome_msg, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def commands_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cmds = sorted(ALLOWED_COMMANDS)
    categories = {
        "File Operations": ['ls', 'cat', 'head', 'tail', 'cp', 'mv', 'rm', 'mkdir', 'touch', 'find', 'tree'],
        "Text Processing": ['grep', 'awk', 'sed', 'cut', 'sort', 'uniq', 'wc', 'tr'],
        "Archives": ['tar', 'zip', 'unzip', 'gzip', 'gunzip'],
        "Network": ['curl', 'wget', 'ping', 'netstat', 'ssh', 'scp'],
        "Git": ['git'],
        "Package Managers": ['pip', 'pip3', 'npm', 'yarn', 'apt', 'apt-get'],
        "Languages": ['python', 'python3', 'node', 'ruby', 'go', 'java', 'php'],
        "Process": ['ps', 'kill', 'top', 'htop', 'nohup', 'screen', 'tmux'],
        "System": ['df', 'du', 'free', 'uptime', 'uname', 'whoami', 'date'],
    }
    
    response = "**Allowed Commands (200+):**\n\n"
    for category, sample_cmds in categories.items():
        available = [c for c in sample_cmds if c in cmds]
        if available:
            response += f"*{category}:* {', '.join(available[:5])}...\n"
    
    response += f"\n**Total: {len(cmds)} commands**\n"
    response += "\nType any command directly to execute!"
    
    await update.message.reply_text(response, parse_mode='Markdown')


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f"Your User ID: `{user_id}`", parse_mode='Markdown')


async def sysinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        uname = subprocess.run(['uname', '-a'], capture_output=True, text=True, timeout=10)
        uptime = subprocess.run(['uptime'], capture_output=True, text=True, timeout=10)
        
        info = f"**System Information:**\n```\n{uname.stdout}\n{uptime.stdout}```"
        await update.message.reply_text(info, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def disk_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = subprocess.run(['df', '-h'], capture_output=True, text=True, timeout=10)
        await update.message.reply_text(f"**Disk Usage:**\n```\n{result.stdout}```", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def memory_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=10)
        await update.message.reply_text(f"**Memory Usage:**\n```\n{result.stdout}```", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


def execute_command(user_id: int, command: str) -> tuple:
    cwd = get_user_cwd(user_id)
    workspace = ensure_workspace(user_id)
    
    command = command.strip()
    if not command:
        return "", "No command provided"
    
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    
    if not parts:
        return "", "No command provided"
    
    if parts[0] == "cd":
        if len(parts) < 2:
            display = cwd.replace(workspace, '~')
            return f"Current directory: {display}", ""
        
        target = parts[1]
        if target == "~":
            new_path = workspace
        elif target == "..":
            new_path = os.path.dirname(cwd)
            if not new_path.startswith(workspace):
                new_path = workspace
        elif target.startswith("/"):
            new_path = os.path.join(workspace, target.lstrip("/"))
        else:
            new_path = os.path.abspath(os.path.join(cwd, target))
        
        if not new_path.startswith(workspace):
            return "", "Cannot navigate outside your workspace."
        
        if set_user_cwd(user_id, new_path):
            display = user_sessions[user_id]['cwd'].replace(workspace, '~')
            return f"Changed directory to {os.path.basename(user_sessions[user_id]['cwd'])}", ""
        else:
            return "", "Directory not found."
    
    is_safe, error = check_command_safety(command, workspace, cwd)
    if not is_safe:
        return "", error
    
    is_background = command.rstrip().endswith('&')
    if is_background or parts[0] == 'nohup':
        return "", "For background processes, use `/run <command>` instead.\nExample: `/run python3 bot.py`"
    
    try:
        env = os.environ.copy()
        env['HOME'] = workspace
        env['USER'] = str(user_id)
        env['PWD'] = cwd
        
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
        
        stdout = result.stdout
        stderr = result.stderr
        
        if len(stdout) > MAX_OUTPUT_LENGTH:
            stdout = stdout[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
        if len(stderr) > MAX_OUTPUT_LENGTH:
            stderr = stderr[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
        
        return stdout, stderr
    
    except subprocess.TimeoutExpired:
        return "", "Command timed out after 60 seconds!"
    except Exception as e:
        return "", f"Error: {str(e)}"


async def handle_terminal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    command = update.message.text.strip()
    
    if not command:
        return
    
    stdout, stderr = execute_command(user_id, command)
    
    response = ""
    if stdout:
        response += f"```\n{stdout}\n```"
    if stderr:
        if response:
            response += "\n"
        response += f"{stderr}"
    
    if not response:
        response = "(No output)"
    
    try:
        await update.message.reply_text(response, parse_mode='Markdown')
    except:
        await update.message.reply_text(response[:4000])


async def run_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "Usage: `/run <command>`\n\n"
            "Examples:\n"
            "- `/run python3 bot.py`\n"
            "- `/run node index.js`\n"
            "- `/run python3 main.py`",
            parse_mode='Markdown'
        )
        return
    
    command = ' '.join(context.args)
    cwd = get_user_cwd(user_id)
    workspace = ensure_workspace(user_id)
    
    is_safe, error = check_command_safety(command, workspace, cwd)
    if not is_safe:
        await update.message.reply_text(error)
        return
    
    process_id = len(running_processes.get(str(user_id), []))
    log_file = os.path.join(workspace, f"process_{process_id}.log")
    
    try:
        env = os.environ.copy()
        env['HOME'] = workspace
        env['PWD'] = cwd
        
        with open(log_file, 'w') as lf:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True
            )
        
        if str(user_id) not in running_processes:
            running_processes[str(user_id)] = []
        
        process_info = {
            "id": process_id,
            "pid": process.pid,
            "command": command,
            "cwd": cwd,
            "log_file": log_file,
            "started": datetime.now().isoformat()
        }
        
        running_processes[str(user_id)].append(process_info)
        save_processes()
        
        await update.message.reply_text(
            f"**Process Started!**\n\n"
            f"ID: `{process_id}`\n"
            f"PID: `{process.pid}`\n"
            f"Command: `{command}`\n\n"
            f"Use `/logs {process_id}` to view output\n"
            f"Use `/stop {process_id}` to stop",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        await update.message.reply_text(f"Failed to start process: {str(e)}")


async def stop_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: `/stop <process_id>`", parse_mode='Markdown')
        return
    
    try:
        process_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid process ID")
        return
    
    user_processes = running_processes.get(str(user_id), [])
    
    if process_id >= len(user_processes):
        await update.message.reply_text("Process not found")
        return
    
    process_info = user_processes[process_id]
    pid = process_info.get("pid")
    
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        await update.message.reply_text(f"Process {process_id} (PID: {pid}) stopped successfully!")
    except ProcessLookupError:
        await update.message.reply_text(f"Process {process_id} was already stopped")
    except Exception as e:
        await update.message.reply_text(f"Error stopping process: {str(e)}")


async def list_processes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_processes = running_processes.get(str(user_id), [])
    
    if not user_processes:
        await update.message.reply_text("No running processes")
        return
    
    response = "**Your Processes:**\n\n"
    
    for proc in user_processes:
        pid = proc.get("pid")
        is_running = False
        try:
            os.kill(pid, 0)
            is_running = True
        except:
            pass
        
        status = "Running" if is_running else "Stopped"
        response += f"**ID {proc['id']}** - {status}\n"
        response += f"  Command: `{proc['command']}`\n"
        response += f"  Started: {proc['started'][:19]}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')


async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: `/logs <process_id>`", parse_mode='Markdown')
        return
    
    try:
        process_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid process ID")
        return
    
    user_processes = running_processes.get(str(user_id), [])
    
    if process_id >= len(user_processes):
        await update.message.reply_text("Process not found")
        return
    
    log_file = user_processes[process_id].get("log_file")
    
    if not os.path.exists(log_file):
        await update.message.reply_text("No logs available yet")
        return
    
    try:
        with open(log_file, 'r') as f:
            logs = f.read()
        
        if not logs:
            await update.message.reply_text("Log file is empty")
            return
        
        if len(logs) > 3500:
            logs = "... (showing last 3500 chars)\n" + logs[-3500:]
        
        await update.message.reply_text(f"**Logs for Process {process_id}:**\n```\n{logs}\n```", parse_mode='Markdown')
    
    except Exception as e:
        await update.message.reply_text(f"Error reading logs: {str(e)}")


async def download_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: `/download <filename>`", parse_mode='Markdown')
        return
    
    filename = ' '.join(context.args)
    cwd = get_user_cwd(user_id)
    workspace = ensure_workspace(user_id)
    
    if filename.startswith('/'):
        file_path = os.path.join(workspace, filename.lstrip('/'))
    else:
        file_path = os.path.join(cwd, filename)
    
    file_path = os.path.abspath(file_path)
    
    if not file_path.startswith(workspace):
        await update.message.reply_text("Cannot access files outside your workspace")
        return
    
    if not os.path.exists(file_path):
        await update.message.reply_text("File not found")
        return
    
    if os.path.isdir(file_path):
        await update.message.reply_text("Cannot download directories. Use `tar` to archive first.")
        return
    
    try:
        await update.message.reply_document(document=open(file_path, 'rb'), filename=os.path.basename(file_path))
    except Exception as e:
        await update.message.reply_text(f"Error downloading: {str(e)}")


async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    cwd = get_user_cwd(user_id)
    workspace = ensure_workspace(user_id)
    
    if not update.message.document:
        display_path = cwd.replace(workspace, '~')
        await update.message.reply_text(
            "**Upload a File**\n\nSend me a file and I'll save it to your current directory.\n\n"
            f"Current: `{display_path}`",
            parse_mode='Markdown'
        )
        return
    
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        filename = update.message.document.file_name or "uploaded_file"
        file_path = os.path.join(cwd, filename)
        
        if not os.path.abspath(file_path).startswith(workspace):
            await update.message.reply_text("Invalid file path")
            return
        
        await file.download_to_drive(file_path)
        
        await update.message.reply_text(f"File saved: `{filename}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Upload failed: {str(e)}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upload_file(update, context)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling update: {context.error}")


def main():
    bot_token = "8523876686:AAHHgxxIxoBIr0T-_7MnYpUFd0OezjD3wvM"
    
    os.makedirs(BASE_WORKSPACES_DIR, exist_ok=True)
    
    load_processes()
    
    start_keep_alive()
    
    app = Application.builder().token(bot_token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_list))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("sysinfo", sysinfo))
    app.add_handler(CommandHandler("disk", disk_usage))
    app.add_handler(CommandHandler("memory", memory_usage))
    app.add_handler(CommandHandler("run", run_process))
    app.add_handler(CommandHandler("stop", stop_process))
    app.add_handler(CommandHandler("ps", list_processes))
    app.add_handler(CommandHandler("logs", view_logs))
    app.add_handler(CommandHandler("download", download_file))
    app.add_handler(CommandHandler("upload", upload_file))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terminal))
    
    app.add_error_handler(error_handler)
    
    print("VPS Bot is starting...")
    print(f"Workspaces directory: {BASE_WORKSPACES_DIR}")
    print("Keep-alive web server started on port 5000")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
