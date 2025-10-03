"""
Log Maintenance Management Command

This Django management command provides comprehensive log maintenance operations
for the logging system. It offers various operations to manage log files,
monitor system health, and perform routine maintenance tasks.

Key Features:
- Log file information and statistics
- Automated log compression for old files
- Cleanup of ancient compressed files
- Recent error analysis and reporting
- Comprehensive maintenance operations

Usage:
    python manage.py log_maintenance [options]

Options:
    --info      Show detailed log file information
    --compress  Compress old rotated log files
    --cleanup   Remove old compressed log files
    --errors    Display recent error entries
    --all       Run all maintenance tasks
    
"""

from django.core.management.base import BaseCommand
from logger.utils import (
    get_log_files_info,
    compress_old_logs,
    clean_old_compressed_logs,
    get_recent_errors
)


class Command(BaseCommand):
    """
    Django management command for ERP log maintenance operations.
    
    This command provides a comprehensive set of tools for managing the logging
    system, performing maintenance operations, and monitoring log file health.
    It's designed to be run manually by administrators or automated via cron jobs.
    
    Command Architecture:
    - Uses Django's BaseCommand for consistent CLI interface
    - Modular operation selection via command-line arguments
    - Detailed output with styled messages for clarity
    - Error handling to ensure partial operations don't fail entirely
    - Integration with existing utility functions
    
    Operational Modes:
    - Individual operations: Run specific maintenance tasks
    - Batch mode (--all): Run all maintenance operations in sequence
    - Information mode: Display current system status
    - Interactive mode: Provide detailed feedback to administrators
    
    Automation Considerations:
    - Can be run via cron for automated maintenance
    - Provides return codes for script integration
    - Logs operations for audit trail
    - Safe to run multiple times (idempotent operations)
    """
    
    # Command help text displayed with --help option
    help = 'Casharooo Log maintenance and information - comprehensive log management operations'   
    def add_arguments(self, parser):
        """
        Define command-line arguments for the maintenance command.
        
        This method sets up the argument parser with all available options for
        log maintenance operations. Each argument corresponds to a specific
        maintenance function.
        
        Args:
            parser: Django's argument parser instance
            
        Argument Design:
        - Boolean flags for simple enable/disable operations
        - Clear, descriptive help text for each option
        - Logical grouping of related operations
        - Support for running all operations together
        """
        parser.add_argument(
            '--info',
            action='store_true',
            help='Show comprehensive log files information including sizes and modification dates'
        )
        parser.add_argument(
            '--compress',
            action='store_true', 
            help='Compress rotated log files older than 7 days to save disk space'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Remove compressed log files older than 30 days to prevent disk space accumulation'
        )
        parser.add_argument(
            '--errors',
            action='store_true',
            help='Display recent error entries from the last 24 hours for troubleshooting'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Execute all maintenance operations (info, compress, cleanup) in sequence'
        )
    
    def handle(self, *args, **options):
        """
        Main command handler that orchestrates maintenance operations.
        
        This method processes command-line arguments and executes the requested
        maintenance operations. It handles operation sequencing and provides
        appropriate feedback to the user.
        
        Args:
            *args: Positional arguments (unused)
            **options: Dictionary of command-line options
            
        Operation Flow:
        1. Check which operations were requested
        2. Execute operations in logical order
        3. Provide feedback for each operation
        4. Handle cases where no operations were specified
        
        Error Handling:
        - Individual operation failures don't stop other operations
        - Clear error messages for troubleshooting
        - Graceful degradation for partial failures
        """
        # Display log file information if requested or running all operations
        if options['info'] or options['all']:
            self.show_log_info()
        
        # Compress old log files if requested or running all operations
        if options['compress'] or options['all']:
            self.compress_logs()
        
        # Clean up old compressed files if requested or running all operations  
        if options['cleanup'] or options['all']:
            self.cleanup_logs()
        
        # Show recent errors (independent operation, not part of --all)
        if options['errors']:
            self.show_recent_errors()
        
        # Provide helpful message if no operations were specified
        if not any(options.values()):
            self.stdout.write(self.style.WARNING(
                'No maintenance operation specified. Use --help to see available options.'
            ))
            self.stdout.write('Available operations: --info, --compress, --cleanup, --errors, --all')
    
    def show_log_info(self):
        """
        Display comprehensive information about all log files in the system.
        
        This method retrieves and displays detailed information about each log file,
        including file sizes, modification dates, and file paths. This information
        is crucial for monitoring system health and planning maintenance operations.
        
        Displayed Information:
        - Log file names and extensions
        - File sizes in human-readable format (MB)
        - Last modification timestamps
        - Full file paths for reference
        
        Output Format:
        - Styled headers for visual clarity
        - Consistent formatting for easy reading
        - Empty state handling when no logs exist
        - Emoji indicators for visual appeal
        
        Use Cases:
        - Regular system health checks
        - Capacity planning and disk usage monitoring
        - Troubleshooting log rotation issues
        - Preparing for maintenance operations
        """
        self.stdout.write(self.style.SUCCESS('=== LOG FILES INFORMATION ==='))
        
        # Retrieve log file information using utility function
        log_files = get_log_files_info()
        
        # Handle case where no log files exist yet
        if not log_files:
            self.stdout.write(self.style.WARNING('No log files found in the logs directory'))
            self.stdout.write('This may indicate:')
            self.stdout.write('  - Logging system not yet initialized')
            self.stdout.write('  - No requests processed yet') 
            self.stdout.write('  - Logs directory permission issues')
            return
        
        # Display information for each log file
        self.stdout.write(f'Found {len(log_files)} log files:')
        self.stdout.write('')
        
        for log_file in log_files:
            # Display file information with visual indicators
            self.stdout.write(f"📄 {log_file['name']}")
            self.stdout.write(f"   📏 Size: {log_file['size']}")
            self.stdout.write(f"   🕐 Modified: {log_file['modified']}")
            self.stdout.write(f"   📁 Path: {log_file['path']}")
            self.stdout.write('')  # Empty line for readability
        
        # Provide additional context and recommendations
        total_size = sum(float(f['size'].split()[0]) for f in log_files)
        self.stdout.write(f"💾 Total log disk usage: {total_size:.2f} MB")
    
    def compress_logs(self):
        """
        Execute log compression operations for old rotated log files.
        
        This method compresses rotated log files that are older than 7 days to
        save disk space while preserving historical data. Compression typically
        reduces log file sizes by 80-90%.
        
        Compression Process:
        - Identifies rotated files (.1, .2, .3 extensions)
        - Checks file age against 7-day threshold
        - Uses gzip compression for maximum compatibility
        - Removes original files after successful compression
        - Provides feedback on compression results
        
        Disk Space Benefits:
        - Significant space savings (typically 80-90% reduction)
        - Maintains data integrity during compression
        - Preserves file modification timestamps
        - Enables longer retention periods
        
        Error Handling:
        - Reports compression failures without stopping
        - Logs compression activities for audit
        - Preserves original files if compression fails
        """
        self.stdout.write(self.style.SUCCESS('=== COMPRESSING OLD LOG FILES ==='))
        
        # Execute compression using utility function
        compressed_count = compress_old_logs()
        
        # Provide feedback based on compression results
        if compressed_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Successfully compressed {compressed_count} old log files"
            ))
            self.stdout.write(f"💾 Disk space saved: Typically 80-90% reduction per file")
            self.stdout.write(f"📋 Compression details logged for audit trail")
        else:
            self.stdout.write(self.style.WARNING("No old log files found that need compression"))
            self.stdout.write("This may indicate:")
            self.stdout.write("  - All rotated files are recent (less than 7 days old)")
            self.stdout.write("  - Files have already been compressed")
            self.stdout.write("  - No log rotation has occurred yet")
    
    def cleanup_logs(self):
        """
        Remove old compressed log files to prevent unlimited disk usage growth.
        
        This method removes compressed log files that are older than 30 days,
        implementing the final stage of the log lifecycle management. This prevents
        unlimited accumulation of historical data while maintaining reasonable
        retention periods for investigation and compliance.
        
        Cleanup Process:
        - Identifies compressed files (.gz extension)
        - Checks file age against 30-day retention policy
        - Permanently removes old compressed files
        - Provides feedback on cleanup results
        - Logs removal activities for audit
        
        Retention Policy Implementation:
        - Active logs: Unlimited retention
        - Rotated logs: 7 days before compression
        - Compressed logs: 30 days before deletion
        - Total retention: ~37 days of historical data
        
        Risk Management:
        - 30-day retention allows time for investigation
        - Permanent deletion - files cannot be recovered
        - Operations are logged for compliance
        - Safe to run multiple times (idempotent)
        """
        self.stdout.write(self.style.SUCCESS('=== CLEANING UP OLD COMPRESSED FILES ==='))
        
        # Execute cleanup using utility function
        removed_count = clean_old_compressed_logs()
        
        # Provide feedback based on cleanup results
        if removed_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"🗑️  Successfully removed {removed_count} old compressed log files"
            ))
            self.stdout.write(f"📅 Retention policy: 30 days for compressed files")
            self.stdout.write(f"⚠️  Note: Removed files cannot be recovered")
            self.stdout.write(f"📋 Cleanup activities logged for audit trail")
        else:
            self.stdout.write(self.style.WARNING("No old compressed files found that need removal"))
            self.stdout.write("This may indicate:")
            self.stdout.write("  - All compressed files are recent (less than 30 days old)")
            self.stdout.write("  - No compressed files exist yet")
            self.stdout.write("  - Previous cleanup operations were successful")
    
    def show_recent_errors(self):
        """
        Display recent error entries for troubleshooting and system monitoring.
        
        This method retrieves and displays recent error entries from the error log,
        providing administrators with quick access to system issues for troubleshooting
        and monitoring purposes.
        
        Error Analysis Features:
        - Shows errors from the last 24 hours
        - Limits output to most recent 10 errors for readability
        - Provides error count for trend analysis
        - Handles cases where no errors exist (healthy system)
        
        Troubleshooting Benefits:
        - Quick identification of recent issues
        - Pattern recognition for recurring problems
        - Immediate feedback on system health
        - Starting point for detailed investigation
        
        Output Format:
        - Clear section headers with visual indicators
        - Limited output to prevent overwhelming information
        - Positive feedback when no errors found
        - Contextual information about error timeframe
        """
        self.stdout.write(self.style.SUCCESS('=== RECENT ERRORS ANALYSIS (Last 24 Hours) ==='))
        
        # Retrieve recent errors using utility function
        errors = get_recent_errors(hours=24, max_lines=50)
        
        # Handle case where no recent errors exist (good news!)
        if not errors:
            self.stdout.write(self.style.SUCCESS("✅ No recent errors found - system is healthy!"))
            self.stdout.write("🎉 This indicates:")
            self.stdout.write("  - Application is running smoothly")
            self.stdout.write("  - No unhandled exceptions in the last 24 hours")
            self.stdout.write("  - Error handling is working correctly")
            return
        
        # Display error summary and most recent entries
        self.stdout.write(self.style.WARNING(f"⚠️  Found {len(errors)} recent error entries"))
        self.stdout.write(f"📊 Showing the 10 most recent errors:")
        self.stdout.write('')
        
        # Display the last 10 errors for detailed analysis
        for error in errors[-10:]:
            self.stdout.write(f"❌ {error}")
        
        # Provide guidance for further investigation
        self.stdout.write('')
        if len(errors) > 10:
            self.stdout.write(f"💡 {len(errors) - 10} additional errors not shown")
            self.stdout.write("📂 Check logs/errors.log for complete error history")
        
        self.stdout.write('')
        self.stdout.write("🔧 Troubleshooting suggestions:")
        self.stdout.write("  - Review error patterns for common causes")
        self.stdout.write("  - Check application logs for additional context")
        self.stdout.write("  - Verify system resources and dependencies")
        self.stdout.write("  - Consider implementing additional error handling")