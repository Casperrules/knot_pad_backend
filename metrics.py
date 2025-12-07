import time
import logging
from typing import Dict, List
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Simple in-memory metrics collector"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.request_counts = defaultdict(int)
        self.request_durations = defaultdict(list)
        self.error_counts = defaultdict(int)
        self.status_codes = defaultdict(int)
        
        # Keep last 1000 requests for analysis
        self.recent_requests = deque(maxlen=1000)
        
        # Track endpoint metrics
        self.endpoint_metrics = defaultdict(lambda: {
            'count': 0,
            'total_duration': 0.0,
            'errors': 0,
            'last_accessed': None
        })
        
        # Track user activity
        self.active_users_today = set()  # User IDs active today
        self.active_users_by_day = defaultdict(set)  # User IDs by date
        self.last_reset_date = datetime.utcnow().date()
    
    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        user_id: str = None
    ):
        """Record a request for metrics"""
        # Check if we need to reset daily user tracking
        today = datetime.utcnow().date()
        if today != self.last_reset_date:
            with self._lock:
                self.active_users_today.clear()
                self.last_reset_date = today
        with self._lock:
            endpoint = f"{method} {path}"
            
            # Update counters
            self.request_counts[endpoint] += 1
            self.status_codes[status_code] += 1
            
            # Track duration
            self.request_durations[endpoint].append(duration)
            if len(self.request_durations[endpoint]) > 100:
                self.request_durations[endpoint].pop(0)
            
            # Track errors
            if status_code >= 400:
                self.error_counts[endpoint] += 1
            
            # Update endpoint metrics
            metrics = self.endpoint_metrics[endpoint]
            metrics['count'] += 1
            metrics['total_duration'] += duration
            metrics['last_accessed'] = datetime.utcnow()
            if status_code >= 400:
                metrics['errors'] += 1
            
            # Track user activity
            if user_id:
                self.active_users_today.add(user_id)
                date_key = datetime.utcnow().date().isoformat()
                self.active_users_by_day[date_key].add(user_id)
            
            # Add to recent requests
            self.recent_requests.append({
                'timestamp': datetime.utcnow(),
                'method': method,
                'path': path,
                'status_code': status_code,
                'duration': duration,
                'user_id': user_id
            })
    
    def get_metrics_summary(self) -> Dict:
        """Get summary of collected metrics"""
        with self._lock:
            total_requests = sum(self.request_counts.values())
            total_errors = sum(self.error_counts.values())
            
            # Calculate average response times
            avg_durations = {}
            for endpoint, durations in self.request_durations.items():
                if durations:
                    avg_durations[endpoint] = sum(durations) / len(durations)
            
            # Top endpoints by request count
            top_endpoints = sorted(
                self.endpoint_metrics.items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )[:10]
            
            # Slowest endpoints
            slowest_endpoints = sorted(
                [
                    (endpoint, metrics['total_duration'] / metrics['count'])
                    for endpoint, metrics in self.endpoint_metrics.items()
                    if metrics['count'] > 0
                ],
                key=lambda x: x[1],
                reverse=True
            )[:10]
            
            return {
                'total_requests': total_requests,
                'total_errors': total_errors,
                'error_rate': (total_errors / total_requests * 100) if total_requests > 0 else 0,
                'status_codes': dict(self.status_codes),
                'top_endpoints': [
                    {
                        'endpoint': endpoint,
                        'count': metrics['count'],
                        'avg_duration': metrics['total_duration'] / metrics['count'],
                        'errors': metrics['errors'],
                        'error_rate': (metrics['errors'] / metrics['count'] * 100) if metrics['count'] > 0 else 0
                    }
                    for endpoint, metrics in top_endpoints
                ],
                'slowest_endpoints': [
                    {'endpoint': endpoint, 'avg_duration': duration}
                    for endpoint, duration in slowest_endpoints
                ]
            }
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        """Get recent error requests"""
        with self._lock:
            errors = [
                req for req in self.recent_requests
                if req['status_code'] >= 400
            ]
            return list(reversed(errors))[:limit]
    
    def get_user_stats(self) -> Dict:
        """Get user activity statistics"""
        with self._lock:
            # Get daily active users for last 7 days
            dau_data = []
            today = datetime.utcnow().date()
            
            for i in range(6, -1, -1):
                date = today - timedelta(days=i)
                date_key = date.isoformat()
                user_count = len(self.active_users_by_day.get(date_key, set()))
                dau_data.append({
                    'date': date_key,
                    'users': user_count
                })
            
            # Calculate total unique users across all time
            all_users = set()
            for users in self.active_users_by_day.values():
                all_users.update(users)
            
            return {
                'daily_active_users': len(self.active_users_today),
                'total_unique_users': len(all_users),
                'dau_history': dau_data
            }
    
    def reset(self):
        """Reset all metrics"""
        with self._lock:
            self.request_counts.clear()
            self.request_durations.clear()
            self.error_counts.clear()
            self.status_codes.clear()
            self.recent_requests.clear()
            self.endpoint_metrics.clear()
            self.active_users_today.clear()
            self.active_users_by_day.clear()
            self.last_reset_date = datetime.utcnow().date()


# Global metrics collector instance
metrics_collector = MetricsCollector()
