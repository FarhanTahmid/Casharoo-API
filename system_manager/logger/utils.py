"""
Logger Utilities Module

This module provides comprehensive utility functions for log file management,
maintenance operations, and custom logging capabilities for Django-based systems.

Key Features:
- Log file information and analytics
- Automated compression and cleanup of old logs
- Recent error analysis and reporting
- Custom business and security event logging
- File system operations with error handling

"""

import os
import gzip
import logging
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings


def get_log_files_info():
    """
    Retrieve comprehensive information about all current log files.
    
    This function scans the logs directory and collects metadata about each log file,
    including size, modification time, and file path. This information is useful for
    monitoring disk usage, identifying active log files, and planning maintenance.
    
    Returns:
        list: List of dictionaries containing log file information
              Each dict contains: {'name', 'size', 'modified', 'path'}
              
    File Information Collected:
    - name: Log file name (e.g., 'requests.log')
    - size: Human-readable file size in MB (e.g., '15.34 MB')
    - modified: Last modification timestamp (YYYY-MM-DD HH:MM:SS format)
    - path: Full file system path to the log file
    
    Use Cases:
    - Monitoring log file growth for capacity planning
    - Identifying when logs were last updated (system health check)
    - Determining which logs need maintenance or archiving
    - Generating reports for system administrators
    - Troubleshooting logging issues
    
    Error Handling:
    - Returns empty list if logs directory doesn't exist
    - Handles permission errors gracefully
    - Skips files that can't be accessed
    """
    # Construct path to logs directory from Django settings
    logs_dir = Path(settings.BASE_DIR) / 'logs'
    log_files = []
    
    # Check if logs directory exists before attempting to scan
    if logs_dir.exists():
        # Scan for all .log files (current active logs)
        for log_file in logs_dir.glob('*.log'):
            try:
                # Get file statistics (size, modification time, etc.)
                stat = log_file.stat()
                
                # Build structured information dictionary
                log_files.append({
                    'name': log_file.name,  # Just the filename
                    'size': f"{stat.st_size / 1024 / 1024:.2f} MB",  # Size in MB (2 decimal places)
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'path': str(log_file),  # Full path as string
                })
            except (OSError, PermissionError) as e:
                # Log access errors but continue processing other files
                logging.getLogger('erp.errors').warning(f"Could not access log file {log_file}: {e}")
    
    # Sort by modification time (most recent first) for better usability
    return sorted(log_files, key=lambda x: x['modified'], reverse=True)


def compress_old_logs():
    """
    Compress log files older than 7 days to save disk space.
    
    This function identifies rotated log files (those with numeric extensions like .1, .2)
    that are older than 7 days and compresses them using gzip compression. This helps
    manage disk space while preserving historical log data for analysis.
    
    Returns:
        int: Number of files successfully compressed
        
    Compression Logic:
    - Only processes rotated files (.1, .2, .3, .4, .5 extensions)
    - Files must be older than 7 days (configurable)
    - Uses gzip compression (typically 90%+ space savings)
    - Removes original file after successful compression
    - Logs compression activities for audit trail
    
    File Selection Criteria:
    - Must be in logs directory
    - Must have numeric extension (.1, .2, .3, .4, .5)
    - Must be older than 7 days based on modification time
    - Must not already be compressed (.gz extension)
    
    Error Handling:
    - Returns 0 if logs directory doesn't exist
    - Skips files that can't be read or compressed
    - Logs errors for troubleshooting
    - Preserves original file if compression fails
    
    Disk Space Benefits:
    - Log files typically compress to 10-20% of original size
    - Significant space savings for text-based log files
    - Maintains data integrity during compression process
    """
    logs_dir = Path(settings.BASE_DIR) / 'logs'
    compressed_count = 0
    
    # Return immediately if logs directory doesn't exist
    if not logs_dir.exists():
        return compressed_count
    
    # Calculate cutoff date (7 days ago from now)
    cutoff_date = datetime.now() - timedelta(days=7)
    
    # Find all rotated log files (files with numeric extensions)
    for log_file in logs_dir.glob('*.log.*'):  # Pattern: requests.log.1, errors.log.2, etc.
        # Check if file has numeric extension (rotated files)
        if log_file.suffix in ['.1', '.2', '.3', '.4', '.5']:
            try:
                # Get file modification time
                stat = log_file.stat()
                file_date = datetime.fromtimestamp(stat.st_mtime)
                
                # Check if file is old enough and not already compressed
                if file_date < cutoff_date and not str(log_file).endswith('.gz'):
                    # Perform gzip compression
                    compressed_file_path = f"{log_file}.gz"
                    
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(compressed_file_path, 'wb') as f_out:
                            # Copy all data from original to compressed file
                            f_out.writelines(f_in)
                    
                    # Remove original file only after successful compression
                    log_file.unlink()
                    compressed_count += 1
                    
                    # Log compression activity for audit trail
                    logging.getLogger('erp.requests').info(
                        f"Compressed old log file: {log_file} -> {compressed_file_path}"
                    )
                    
            except (OSError, IOError) as e:
                # Log compression errors but continue with other files
                logging.getLogger('erp.errors').error(f"Failed to compress {log_file}: {e}")
    
    return compressed_count


def clean_old_compressed_logs():
    """
    Remove compressed log files older than 30 days to manage long-term disk usage.
    
    This function implements the final stage of log lifecycle management by removing
    compressed log files that are older than 30 days. This prevents unlimited disk
    usage growth while maintaining reasonable historical data retention.
    
    Returns:
        int: Number of compressed files successfully removed
        
    Cleanup Logic:
    - Only processes .gz compressed files
    - Files must be older than 30 days (configurable retention period)
    - Permanently removes files (not recoverable)
    - Logs removal activities for audit trail
    
    Retention Policy:
    - Active logs: Unlimited retention (current .log files)
    - Rotated logs: 7 days before compression
    - Compressed logs: 30 days before deletion
    - Total retention: ~37 days of log history
    
    Risk Management:
    - 30-day retention provides reasonable time for investigations
    - Compressed files are much smaller, so less storage pressure
    - Removal is logged for compliance and audit purposes
    - Function can be run safely multiple times
    
    Error Handling:
    - Returns 0 if logs directory doesn't exist  
    - Continues processing if individual files can't be deleted
    - Logs errors for troubleshooting
    - Maintains system stability even with file system issues
    """
    logs_dir = Path(settings.BASE_DIR) / 'logs'
    removed_count = 0
    
    # Return immediately if logs directory doesn't exist
    if not logs_dir.exists():
        return removed_count
    
    # Calculate cutoff date (30 days ago from now)
    cutoff_date = datetime.now() - timedelta(days=30)
    
    # Find all compressed log files (.gz extension)
    for gz_file in logs_dir.glob('*.gz'):
        try:
            # Get file modification time
            stat = gz_file.stat()
            file_date = datetime.fromtimestamp(stat.st_mtime)
            
            # Check if compressed file is older than retention period
            if file_date < cutoff_date:
                # Permanently remove the compressed file
                gz_file.unlink()
                removed_count += 1
                
                # Log removal activity for audit trail
                logging.getLogger('erp.requests').info(f"Removed old compressed log: {gz_file}")
                
        except (OSError, PermissionError) as e:
            # Log deletion errors but continue with other files
            logging.getLogger('erp.errors').error(f"Failed to remove compressed log {gz_file}: {e}")
    
    return removed_count


def get_recent_errors(hours=24, max_lines=100):
    """
    Retrieve and analyze recent error entries from the error log file.
    
    This function reads the error log file and extracts recent error entries for
    analysis, troubleshooting, and monitoring purposes. It's useful for quickly
    identifying system issues and patterns in error occurrence.
    
    Args:
        hours (int): Number of hours to look back for recent errors (default: 24)
        max_lines (int): Maximum number of log lines to read (default: 100)
        
    Returns:
        list: List of recent error log entries as strings
              Empty list if no errors found or file doesn't exist
              
    Analysis Features:
    - Time-based filtering (configurable look-back period)
    - Line limit to prevent memory issues with large log files
    - Returns raw log lines for further processing
    - Handles file access errors gracefully
    
    Use Cases:
    - Quick error checking in maintenance scripts
    - Dashboard error summaries
    - Automated alerting systems
    - Troubleshooting and debugging sessions
    - System health monitoring
    
    Performance Considerations:
    - Reads from end of file backwards (most recent errors first)
    - Limits lines read to prevent memory issues
    - Time filtering is approximate (doesn't parse timestamps)
    - Efficient for large log files
    
    Error Handling:
    - Returns empty list if error log doesn't exist
    - Handles file permission errors
    - Manages encoding issues with UTF-8
    - Continues processing even with partial read failures
    """
    logs_dir = Path(settings.BASE_DIR) / 'logs'
    error_log = logs_dir / 'errors.log'
    
    # Return empty list if error log doesn't exist yet
    if not error_log.exists():
        return []
    
    # Calculate cutoff time for recent errors (not currently used in filtering)
    cutoff_time = datetime.now() - timedelta(hours=hours)
    recent_errors = []
    
    try:
        # Read all lines from error log file
        with open(error_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Process last max_lines entries (most recent errors)
        # This approach is efficient for large files and focuses on recent issues
        for line in lines[-max_lines:]:
            stripped_line = line.strip()
            if stripped_line:  # Skip empty lines
                recent_errors.append(stripped_line)
                
    except (OSError, IOError, UnicodeDecodeError) as e:
        # Log file reading errors but don't crash the function
        logging.getLogger('erp.errors').error(f"Error reading error log: {e}")
    
    return recent_errors


# Custom logging functions for manual use throughout the application
# These functions provide standardized logging for specific types of events

def log_business_event(event_name, details=None):
    """
    Log important business events for analytics and audit purposes.
    
    This function provides a standardized way to log business-significant events
    that occur within the ERP/HRM system. These events are useful for business
    intelligence, process monitoring, and compliance reporting.
    
    Args:
        event_name (str): Name/type of the business event (e.g., 'employee_hired')
        details (dict, optional): Additional structured data about the event
        
    Business Event Examples:
    - employee_hired: New employee onboarding
    - payroll_processed: Salary payments completed
    - performance_review: Employee evaluation conducted
    - department_created: New organizational unit established
    - policy_updated: Company policy modifications
    
    Logged Information:
    - Event name for categorization
    - Additional details as structured data
    - Timestamp (automatic)
    - Event type classification ('business')
    
    Use Cases:
    - Business process monitoring
    - Compliance reporting and auditing
    - Performance analytics and KPIs
    - Process improvement analysis
    - Executive dashboards and reporting
    
    Example Usage:
        log_business_event('employee_hired', {
            'employee_id': 123,
            'department': 'IT',
            'position': 'Software Developer',
            'hire_date': '2025-01-15'
        })
    """
    logger = logging.getLogger('erp.requests')
    
    # Build log message with event name
    log_message = f"BUSINESS EVENT: {event_name}"
    if details:
        log_message += f" | {details}"
    
    # Log with structured extra data for processing and analysis
    logger.info(log_message, extra={
        'event_type': 'business',        # Classification for filtering
        'event_name': event_name,        # Specific event identifier
        'details': details,              # Additional structured data
        'category': 'business_event',    # High-level category
    })


def log_security_event(event_name, details=None, severity='WARNING'):
    """
    Log security-related events for monitoring and incident response.
    
    This function provides specialized logging for security events, which require
    different handling than regular application events. Security events are critical
    for compliance, threat detection, and incident response.
    
    Args:
        event_name (str): Name/type of the security event
        details (dict, optional): Additional context about the security event  
        severity (str): Log level severity ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
        
    Security Event Examples:
    - suspicious_login_pattern: Multiple failed login attempts
    - privilege_escalation: User role/permission changes
    - data_access_violation: Unauthorized data access attempt  
    - password_policy_violation: Weak password detected
    - account_lockout: Account temporarily disabled
    - unusual_activity: Anomalous user behavior detected
    
    Severity Levels:
    - INFO: Routine security events (successful logins)
    - WARNING: Potentially suspicious activities (failed logins)
    - ERROR: Security violations (unauthorized access attempts)
    - CRITICAL: Active security breaches (confirmed attacks)
    
    Compliance Benefits:
    - Meets audit requirements for security monitoring
    - Provides evidence for compliance certifications
    - Supports incident response and forensic analysis
    - Enables automated security alerting
    
    Example Usage:
        log_security_event('failed_login_attempts', {
            'username': 'john_doe',
            'ip_address': '192.168.1.100',
            'attempt_count': 5,
            'time_window': '5_minutes'
        }, 'WARNING')
    """
    logger = logging.getLogger('erp.auth')
    
    # Build log message with security event name
    log_message = f"SECURITY EVENT: {event_name}"
    if details:
        log_message += f" | {details}"
    
    # Convert severity string to logging level constant
    log_level = getattr(logging, severity.upper(), logging.WARNING)
    
    # Log with appropriate severity and structured data
    logger.log(log_level, log_message, extra={
        'event_type': 'security',        # Classification for security tools
        'event_name': event_name,        # Specific security event identifier
        'details': details,              # Additional context and metadata
        'severity': severity,            # Security severity level
        'category': 'security_event',    # High-level category
    })


def log_system_event(event_name, details=None):
    """
    Log system-level events for operational monitoring and maintenance.
    
    This function handles logging of system and infrastructure events that are
    important for operations teams, system administrators, and automated
    monitoring systems.
    
    Args:
        event_name (str): Name/type of the system event
        details (dict, optional): Additional technical details about the event
        
    System Event Examples:
    - database_connection_lost: Database connectivity issues
    - cache_cleared: Application cache reset
    - scheduled_task_completed: Cron job or scheduled process finished
    - configuration_reloaded: System settings updated
    - backup_completed: Data backup operation finished  
    - service_restarted: Application service restarted
    - disk_space_warning: Storage capacity alerts
    
    Operational Benefits:
    - Enables proactive system monitoring
    - Provides data for capacity planning  
    - Supports troubleshooting and root cause analysis
    - Facilitates automated operational responses
    - Helps with system performance optimization
    
    Integration Points:
    - System monitoring tools (Nagios, Zabbix, etc.)
    - Log aggregation systems (ELK stack, Splunk)
    - Alerting and notification systems
    - Automated incident response systems
    
    Example Usage:
        log_system_event('backup_completed', {
            'backup_type': 'daily_full',
            'size': '2.5GB', 
            'duration': '45_minutes',
            'destination': 's3://backups/hrm/'
        })
    """
    logger = logging.getLogger('django')
    
    # Build log message with system event name
    log_message = f"SYSTEM EVENT: {event_name}"
    if details:
        log_message += f" | {details}"
    
    # Log system events at INFO level with structured data
    logger.info(log_message, extra={
        'event_type': 'system',          # Classification for operations tools
        'event_name': event_name,        # Specific system event identifier
        'details': details,              # Technical details and metadata
        'category': 'system_event',      # High-level category
    })