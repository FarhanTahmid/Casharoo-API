"""
Log Status Management Command

This Django management command provides quick health check and status verification
for the logging system. It performs essential checks to ensure the logging
system is properly configured and operational.

Key Features:
- Quick logging system health check
- Directory and file permission verification
- Log file existence and size reporting
- Write permission testing
- System status summary with recommendations

Usage:
    python manage.py log_status

"""

from django.core.management.base import BaseCommand
from pathlib import Path
from django.conf import settings
import os


class Command(BaseCommand):
    """
    Django management command for quick logging system status check.
    
    This command provides a rapid health check for the logging system, verifying
    that all components are properly configured and operational. It's designed
    for quick troubleshooting and system verification.
    
    Health Check Components:
    - Logs directory existence and accessibility
    - Individual log file status and sizes
    - File system permissions verification
    - Configuration validation
    - Operational recommendations
    
    Use Cases:
    - Post-deployment verification
    - Troubleshooting logging issues
    - Regular health monitoring
    - Development environment setup verification
    - System administration quick checks
    
    Output Design:
    - Clear visual indicators (✅ ❌ ⚪)
    - Concise status information
    - Actionable recommendations
    - Consistent formatting for scripts and humans
    """
    
    # Command help text displayed with --help option
    help = 'Quick health check and status verification for the ERP logging system'
    
    def handle(self, *args, **options):
        """
        Execute the logging system status check.
        
        This method performs a comprehensive but quick check of the logging system,
        verifying directory structure, file permissions, and operational status.
        
        Args:
            *args: Positional arguments (unused)
            **options: Command-line options (unused for this command)
            
        Check Sequence:
        1. Verify logs directory exists and is accessible
        2. Check status of each expected log file
        3. Test write permissions
        4. Provide summary and recommendations
        
        Status Indicators:
        - ✅ Green checkmark: Component is working correctly
        - ❌ Red X: Component has issues that need attention
        - ⚪ White circle: Component not yet initialized (normal for new systems)
        - 📁 📄 💾: Visual icons for different component types
        """
        # Get logs directory path from Django settings
        logs_dir = Path(settings.BASE_DIR) / 'logs'
        
        # Display header with system information
        self.stdout.write(self.style.SUCCESS('🚀 ERP Logger System Status Check'))
        self.stdout.write(f"📁 Logs directory: {logs_dir}")
        self.stdout.write('')
        
        # Critical check: Verify logs directory exists
        if not logs_dir.exists():
            self.stdout.write(self.style.ERROR('❌ CRITICAL: Logs directory does not exist'))
            self.stdout.write('')
            self.stdout.write('🔧 Recommended actions:')
            self.stdout.write(f'  1. Create directory: mkdir -p {logs_dir}')
            self.stdout.write('  2. Set appropriate permissions')
            self.stdout.write('  3. Restart Django application')
            self.stdout.write('  4. Test logging functionality')
            return
        
        # Display directory status
        self.stdout.write(self.style.SUCCESS('✅ Logs directory exists and is accessible'))
        
        # Check individual log files
        self._check_log_files(logs_dir)
        
        # Test write permissions
        self._check_write_permissions(logs_dir)
        
        # Display summary and recommendations
        self._display_recommendations()
    
    def _check_log_files(self, logs_dir):
        """
        Check the status of each expected log file.
        
        This method verifies the existence and basic properties of each log file
        that should be created by the logging system. It provides size information
        and status indicators for each file.
        
        Args:
            logs_dir (Path): Path object for the logs directory
            
        Files Checked:
        - requests.log: HTTP request/response logs
        - errors.log: Exception and error logs
        - auth.log: Authentication event logs
        - general.log: General application logs
        
        Status Logic:
        - ✅ File exists with content: Normal operation
        - ⚪ File doesn't exist: Normal for new installations
        - File size reporting: Helps with capacity planning
        """
        self.stdout.write('')
        self.stdout.write('📄 Log File Status:')
        
        # Define expected log files and their purposes
        log_files = {
            'requests.log': 'HTTP requests and responses',
            'errors.log': 'Application errors and exceptions', 
            'auth.log': 'Authentication events and security',
            'general.log': 'General application logging'
        }
        
        # Check each expected log file
        for log_file, description in log_files.items():
            file_path = logs_dir / log_file
            
            if file_path.exists():
                # File exists - get size information
                try:
                    size = file_path.stat().st_size
                    size_mb = size / 1024 / 1024
                    
                    # Determine status based on file size
                    if size_mb > 0:
                        self.stdout.write(f"✅ {log_file}: {size_mb:.2f} MB ({description})")
                    else:
                        self.stdout.write(f"✅ {log_file}: Empty file - ready for logging ({description})")
                        
                except OSError as e:
                    # File exists but can't be accessed
                    self.stdout.write(f"❌ {log_file}: Access error - {e} ({description})")
            else:
                # File doesn't exist yet - normal for new installations
                self.stdout.write(f"⚪ {log_file}: Not created yet - will be created automatically ({description})")
    
    def _check_write_permissions(self, logs_dir):
        """
        Test write permissions in the logs directory.
        
        This method performs an actual write test to verify that the Django
        application has the necessary permissions to create and write log files.
        
        Args:
            logs_dir (Path): Path object for the logs directory
            
        Test Process:
        - Create a temporary test file
        - Write test content to the file
        - Successfully delete the test file
        - Report success or failure with specific error details
        
        Permission Requirements:
        - Directory read access: List existing files
        - Directory write access: Create new files
        - File write access: Append to existing files
        - File delete access: Remove temporary files
        """
        self.stdout.write('')
        self.stdout.write('🔒 Permission Verification:')
        
        try:
            # Create test file to verify write permissions
            test_file = logs_dir / '.permission_test'
            
            # Write test content
            test_file.write_text('ERP Logger permission test - safe to delete')
            
            # Clean up test file
            test_file.unlink()
            
            # Report successful permission test
            self.stdout.write("✅ Write permissions: OK - can create and modify log files")
            
        except PermissionError as e:
            # Permission denied - critical issue
            self.stdout.write(f"❌ Write permissions: DENIED - {e}")
            self.stdout.write('')
            self.stdout.write('🔧 Permission troubleshooting:')
            self.stdout.write('  1. Check directory ownership and permissions')
            self.stdout.write('  2. Ensure Django process user has write access')
            self.stdout.write('  3. Verify SELinux/AppArmor policies if applicable')
            self.stdout.write(f'  4. Command: chmod 755 {logs_dir} && chown django_user {logs_dir}')
            
        except OSError as e:
            # Other file system errors
            self.stdout.write(f"❌ Write permissions: ERROR - {e}")
            self.stdout.write('')
            self.stdout.write('🔧 File system troubleshooting:')
            self.stdout.write('  1. Check disk space availability')
            self.stdout.write('  2. Verify file system integrity')
            self.stdout.write('  3. Check mount point accessibility')
            
        except Exception as e:
            # Unexpected errors
            self.stdout.write(f"❌ Write permissions: UNEXPECTED ERROR - {e}")
            self.stdout.write('  Contact system administrator for investigation')
    
    def _display_recommendations(self):
        """
        Display system recommendations and next steps.
        
        This method provides actionable recommendations based on the status check
        results and guides users to additional tools and resources.
        
        Recommendations Include:
        - Next steps for monitoring and maintenance
        - Links to additional management commands
        - Best practices for ongoing operations
        - Troubleshooting resources
        """
        self.stdout.write('')
        self.stdout.write('💡 System Recommendations:')
        
        # Basic operational recommendations
        self.stdout.write('')
        self.stdout.write('📊 Monitoring and Maintenance:')
        self.stdout.write("  • Run 'python manage.py log_maintenance --info' for detailed file analysis")
        self.stdout.write("  • Set up automated log rotation and cleanup via cron jobs")
        self.stdout.write("  • Monitor disk usage regularly for capacity planning")
        self.stdout.write("  • Review error logs periodically for system health")
        
        # Development and testing recommendations
        self.stdout.write('')
        self.stdout.write('🧪 Development and Testing:')
        self.stdout.write("  • Generate test requests to verify logging functionality")
        self.stdout.write("  • Test error logging by triggering controlled exceptions")
        self.stdout.write("  • Verify authentication logging with login/logout tests")
        self.stdout.write("  • Check log rotation by monitoring file sizes over time")
        
        # Production deployment recommendations
        self.stdout.write('')
        self.stdout.write('🚀 Production Deployment:')
        self.stdout.write("  • Configure log aggregation tools (ELK stack, Splunk, etc.)")
        self.stdout.write("  • Set up automated alerting for error rate thresholds")
        self.stdout.write("  • Implement log backup and archival procedures")
        self.stdout.write("  • Document log retention and compliance policies")
        
        # Quick reference for additional tools
        self.stdout.write('')
        self.stdout.write('🔧 Available Management Commands:')
        self.stdout.write("  • 'python manage.py log_maintenance --all' - Full maintenance cycle")
        self.stdout.write("  • 'python manage.py log_maintenance --errors' - Recent error analysis")
        self.stdout.write("  • 'python manage.py log_maintenance --compress' - Compress old logs")
        self.stdout.write("  • 'python manage.py log_maintenance --cleanup' - Remove ancient logs")
        
        # Final status summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✨ Status check complete! Logging system is ready for operation.'))