"""
Logger Middleware Module

This module provides comprehensive logging capabilities for Django-based systems.
It automatically captures all HTTP requests, responses, and exceptions without requiring
manual logging implementation throughout the application.

Key Features:
- Automatic request/response logging with performance metrics
- Exception handling with API-friendly error responses
- IP address extraction from various proxy configurations
- Integration with Django's logging framework
- Zero-configuration setup for basic logging needs

"""

import logging
import time
import json
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse

# Initialize specialized loggers for different types of events
# These loggers are configured in Django settings.py and route to different files
request_logger = logging.getLogger('casharooo.requests')  # HTTP requests/responses
error_logger = logging.getLogger('casharooo.errors')      # Exceptions and errors
auth_logger = logging.getLogger('casharooo.auth')         # Authentication events


class LoggerMiddleware(MiddlewareMixin):
    """
    Comprehensive logging middleware for Casharooo system.
    
    This middleware automatically intercepts and logs all HTTP traffic passing through
    the Django application. It provides detailed logging of requests, responses, and
    exceptions without requiring developers to manually add logging code.
    
    The middleware integrates with Django's request/response cycle at three key points:
    1. process_request: Captures incoming request details
    2. process_response: Logs response details and performance metrics  
    3. process_exception: Handles and logs unhandled exceptions
    
    Usage:
        Add 'system_manager.logger.middleware.LoggerMiddleware' to MIDDLEWARE in settings.py
        
    Thread Safety:
        This middleware is thread-safe and suitable for production use with multiple
        workers and concurrent requests.
    """
    
    def process_request(self, request):
        """
        Process incoming HTTP requests and log relevant details.
        
        This method is called for every incoming request before it reaches the view.
        It captures essential metadata about the request and starts performance timing.
        
        Args:
            request (HttpRequest): Django request object containing all request data
            
        Returns:
            None: Always returns None to continue normal request processing
            
        Logged Information:
        - HTTP method (GET, POST, PUT, DELETE, etc.)
        - Request path/URL
        - User information (username or 'anonymous')
        - Client IP address (handles proxy configurations)
        - User-Agent string for client identification
        - Timestamp for request arrival
        
        Performance Considerations:
        - Minimal overhead added to request processing
        - IP extraction handles common proxy headers efficiently
        - User information safely extracted with fallback to 'anonymous'
        """
        # Record start time for response time calculation
        # This timestamp will be used in process_response to measure total request duration
        request.start_time = time.time()
        
        # Extract user information safely
        # getattr() provides safe access with fallback to 'anonymous' if user not authenticated
        username = getattr(request.user, 'username', 'anonymous')
        
        # Get client IP address through proxy-aware method
        client_ip = self.get_client_ip(request)
        
        # Get user agent for client identification and security monitoring
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Log the incoming request with structured data
        # Using 'extra' parameter provides additional structured data for log processors
        request_logger.info(
            f"REQUEST: {request.method} {request.path}", 
            extra={
                'method': request.method,           # HTTP method for filtering/analysis
                'path': request.path,               # URL path for endpoint tracking
                'user': username,                   # User identification for audit trails
                'ip': client_ip,                    # Client IP for security monitoring
                'user_agent': user_agent,           # Client info for analytics
                'event_type': 'request',            # Event classification
            }
        )
        
        # Return None to continue normal Django request processing
        return None
    
    def process_response(self, request, response):
        """
        Process HTTP responses and log performance and status information.
        
        This method is called after the view has processed the request and generated
        a response. It logs response details, calculates performance metrics, and
        determines appropriate log levels based on HTTP status codes.
        
        Args:
            request (HttpRequest): The original request object
            response (HttpResponse): The response generated by the view
            
        Returns:
            HttpResponse: The original response object (unmodified)
            
        Logged Information:
        - HTTP status code
        - Response time in seconds (3 decimal precision)
        - Request method and path (for correlation with request logs)
        - User and IP information
        - Log level based on status code (INFO/WARNING/ERROR)
        
        Log Level Logic:
        - 5xx status codes: ERROR level (server errors)
        - 4xx status codes: WARNING level (client errors)  
        - 2xx/3xx status codes: INFO level (successful requests)
        
        Performance Monitoring:
        - Tracks response times for performance analysis
        - Helps identify slow endpoints and performance bottlenecks
        - Provides data for SLA monitoring and capacity planning
        """
        # Calculate response time if start time was recorded
        if hasattr(request, 'start_time'):
            response_time = time.time() - request.start_time
        else:
            # Fallback if start_time wasn't set (shouldn't happen in normal operation)
            response_time = 0
            
        # Extract status code for logging and log level determination
        status_code = response.status_code
        
        # Determine appropriate log level based on HTTP status code
        # This helps with log filtering and alerting setup
        if status_code >= 500:
            # Server errors (500-599) are logged as ERROR
            # These indicate problems with the application or server
            log_level = logging.ERROR
        elif status_code >= 400:
            # Client errors (400-499) are logged as WARNING
            # These include authentication failures, not found errors, etc.
            log_level = logging.WARNING
        else:
            # Success codes (200-399) are logged as INFO
            # These represent normal, successful request processing
            log_level = logging.INFO
        
        # Extract user and IP information (same as in process_request)
        username = getattr(request.user, 'username', 'anonymous')
        client_ip = self.get_client_ip(request)
        
        # Log the response with performance and status information
        request_logger.log(
            log_level,
            f"RESPONSE: {request.method} {request.path} - {status_code}",
            extra={
                'method': request.method,               # HTTP method
                'path': request.path,                   # URL path
                'status_code': status_code,             # HTTP response code
                'response_time': round(response_time, 3), # Response time (ms precision)
                'user': username,                       # User identification
                'ip': client_ip,                        # Client IP
                'event_type': 'response',               # Event classification
            }
        )
        
        # Return the original response unchanged
        return response
    
    def process_exception(self, request, exception):
        """
        Handle and log unhandled exceptions that occur during request processing.
        
        This method is called when an unhandled exception occurs anywhere in the
        request processing pipeline. It provides comprehensive error logging and
        returns appropriate error responses for API endpoints.
        
        Args:
            request (HttpRequest): The request being processed when exception occurred
            exception (Exception): The unhandled exception that was raised
            
        Returns:
            JsonResponse: For API endpoints, returns structured JSON error
            None: For non-API endpoints, returns None to use Django's default error handling
            
        Logged Information:
        - Exception type and message
        - Full stack trace (via exc_info=True)
        - Request details (method, path, user, IP)
        - Timestamp of exception occurrence
        
        API Error Response:
        - Returns structured JSON for endpoints starting with '/api/'
        - Provides generic error message (doesn't expose sensitive details)
        - Uses HTTP 500 status code
        - Includes error code for client-side handling
        
        Security Considerations:
        - Doesn't expose sensitive exception details in API responses
        - Logs full details for debugging while keeping API responses generic
        - IP tracking helps identify potential security issues
        """
        # Extract user and IP information for security tracking
        username = getattr(request.user, 'username', 'anonymous')
        client_ip = self.get_client_ip(request)
        
        # Log the exception with full details for debugging
        # exc_info=True includes the full stack trace in the log
        error_logger.error(
            f"EXCEPTION: {request.method} {request.path} - {str(exception)}",
            extra={
                'method': request.method,                    # HTTP method
                'path': request.path,                        # URL where exception occurred
                'exception_type': exception.__class__.__name__, # Exception class name
                'exception_message': str(exception),         # Exception message
                'user': username,                            # User context
                'ip': client_ip,                            # Client IP for security
                'event_type': 'exception',                   # Event classification
            },
            exc_info=True  # Include full stack trace in log output
        )
        
        # Provide structured error response for API endpoints
        # This ensures consistent error handling for frontend applications
        if request.path.startswith('/api/'):
            return JsonResponse({
                'error': 'Internal server error',      # Generic user-friendly message
                'code': 'INTERNAL_ERROR'               # Error code for client handling
            }, status=500)
        
        # For non-API endpoints, return None to use Django's default error handling
        # This allows normal error pages to be displayed for web interface
        return None
    
    def get_client_ip(self, request):
        """
        Extract the real client IP address from the request.
        
        This method handles various proxy configurations and load balancers that
        may modify or add headers containing the original client IP address.
        
        Args:
            request (HttpRequest): Django request object
            
        Returns:
            str: Client IP address as a string
            
        IP Extraction Logic:
        1. Check X-Forwarded-For header (most common proxy header)
        2. Take the first IP in the chain (closest to original client)
        3. Fall back to REMOTE_ADDR if no proxy headers present
        
        Proxy Header Handling:
        - X-Forwarded-For can contain multiple IPs: "client_ip, proxy1_ip, proxy2_ip"
        - We want the first IP (leftmost) which represents the original client
        - Handles cases where proxies add their own IPs to the chain
        
        Security Notes:
        - IP addresses are used for security monitoring and audit trails
        - Accurate IP extraction is crucial for rate limiting and abuse detection
        - Consider IP validation if implementing security features based on IPs
        """
        # Check for X-Forwarded-For header (standard proxy header)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        
        if x_forwarded_for:
            # X-Forwarded-For may contain multiple IPs separated by commas
            # Format: "original_client_ip, proxy1_ip, proxy2_ip, ..."
            # We want the first IP which represents the original client
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            # Fall back to REMOTE_ADDR if no proxy headers are present
            # This is the direct connection IP (may be a proxy in load-balanced setups)
            ip = request.META.get('REMOTE_ADDR')
        
        return ip


class AuthenticationLoggingMixin:
    """
    Mixin class for adding authentication-specific logging to existing middleware.
    
    This mixin provides specialized logging methods for authentication events,
    which are crucial for security monitoring, compliance, and audit requirements.
    It's designed to be mixed into existing authentication middleware classes.
    
    Usage:
        class YourAuthMiddleware(AuthenticationLoggingMixin, BaseMiddleware):
            def process_request(self, request):
                # Your authentication logic here
                if authentication_successful:
                    self.log_auth_success(request, username)
                else:
                    self.log_auth_failure(request, failure_reason)
                    
    Security Compliance:
    - Helps meet audit requirements for user access tracking
    - Provides data for security incident investigation
    - Enables detection of suspicious authentication patterns
    - Supports compliance with standards like SOX, HIPAA, PCI-DSS
    
    Integration Notes:
    - Designed to be non-intrusive to existing authentication logic
    - Uses dedicated auth logger for separate log file management
    - Includes IP tracking for geographic and security analysis
    """
    
    def log_auth_success(self, request, username):
        """
        Log successful authentication events.
        
        Records when users successfully authenticate to the system. This information
        is crucial for audit trails and security monitoring.
        
        Args:
            request (HttpRequest): The request object for the authentication attempt
            username (str): The username that successfully authenticated
            
        Logged Information:
        - Username for audit trail
        - Client IP address for security monitoring
        - Request path where authentication occurred
        - HTTP method used for authentication
        - Timestamp of successful authentication
        
        Use Cases:
        - Audit trail for compliance requirements
        - User activity monitoring
        - Security analysis and pattern detection
        - Login success rate analytics
        """
        auth_logger.info(
            f"AUTH SUCCESS: {username}",
            extra={
                'username': username,                    # Authenticated user
                'ip': self.get_client_ip(request),      # Client IP for security
                'path': request.path,                    # Where auth occurred
                'method': request.method,                # HTTP method used
                'event_type': 'auth_success',            # Event classification
                'auth_result': 'success',                # Authentication result
            }
        )
    
    def log_auth_failure(self, request, reason):
        """
        Log failed authentication attempts.
        
        Records when authentication attempts fail, including the reason for failure.
        This is critical for security monitoring and detecting potential attacks.
        
        Args:
            request (HttpRequest): The request object for the failed authentication
            reason (str): Reason for authentication failure (e.g., 'invalid_password', 
                         'user_not_found', 'account_locked')
                         
        Logged Information:
        - Failure reason for security analysis
        - Client IP address for threat detection
        - Request path and method
        - Timestamp of failed attempt
        
        Security Applications:
        - Brute force attack detection
        - Failed login rate monitoring
        - Suspicious IP identification
        - Account compromise detection
        - Geographic anomaly detection
        
        Common Failure Reasons:
        - 'invalid_password': Wrong password provided
        - 'user_not_found': Username doesn't exist
        - 'account_locked': Account temporarily locked
        - 'account_disabled': Account permanently disabled  
        - 'invalid_token': Authentication token invalid/expired
        """
        auth_logger.warning(
            f"AUTH FAILED: {reason}",
            extra={
                'reason': reason,                        # Why authentication failed
                'ip': self.get_client_ip(request),      # Client IP for security analysis
                'path': request.path,                    # Where auth was attempted
                'method': request.method,                # HTTP method used
                'event_type': 'auth_failure',            # Event classification
                'auth_result': 'failure',                # Authentication result
            }
        )
    
    def get_client_ip(self, request):
        """
        Extract the real client IP address from the request.
        
        Identical implementation to ERPLoggerMiddleware.get_client_ip().
        Duplicated here to avoid dependencies between classes and ensure
        the mixin can be used independently.
        
        Args:
            request (HttpRequest): Django request object
            
        Returns:
            str: Client IP address as a string
            
        See ERPLoggerMiddleware.get_client_ip() for detailed documentation.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip