###############################################################################
# AUTOMATIC FILE CLEANUP MANAGER
# Prevents storage accumulation with age-based, size-based, and orphaned session cleanup
###############################################################################

import os
import time
import logging
import threading
import schedule
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


###############################################################################
# CLEANUP MANAGER CLASS
# Production-ready file lifecycle management
###############################################################################

class CleanupManager:
    """Automated file cleanup system - O(n) operations where n is file count"""
    
    def __init__(self, upload_folder: str = 'uploads', result_folders: List[str] = None,
                 max_age_hours: int = 24, max_total_size_mb: int = 100, 
                 cleanup_interval_hours: int = 1):
        
        self.upload_folder = os.path.abspath(upload_folder)
        self.result_folders = [os.path.abspath(folder) 
                              for folder in (result_folders or ['results', 'separate_results'])]
        
        self.max_age_hours = max_age_hours
        self.max_total_size_mb = max_total_size_mb
        self.cleanup_interval_hours = cleanup_interval_hours
        self.running = False
        self.cleanup_thread = None
        
        for folder in [self.upload_folder] + self.result_folders:
            os.makedirs(folder, exist_ok=True)


###############################################################################
# BACKGROUND SERVICE MANAGEMENT
# Thread-based cleanup scheduling
###############################################################################

    def start_background_cleanup(self):
        """Initialize background cleanup services - O(1) complexity"""
        if self.running:
            logger.warning("Cleanup manager already running")
            return
            
        self.running = True
        
        schedule.every(self.cleanup_interval_hours).hours.do(self._cleanup_old_files)
        schedule.every(30).minutes.do(self._cleanup_by_size)
        schedule.every(6).hours.do(self._cleanup_orphaned_sessions)
        
        self.cleanup_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.cleanup_thread.start()
        
        logger.info(f"Background cleanup started - {self.max_age_hours}h age limit, {self.max_total_size_mb}MB size limit")

    def stop_background_cleanup(self):
        """Stop background cleanup"""
        self.running = False
        schedule.clear()
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)

    def _run_scheduler(self):
        """Background scheduler loop - O(1) per iteration"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Cleanup scheduler error: {e}")


###############################################################################
# AGE-BASED CLEANUP
# Remove files older than specified age
###############################################################################

    def _cleanup_old_files(self):
        """Age-based file cleanup - O(n) where n is total file count"""
        try:
            cutoff_time = time.time() - (self.max_age_hours * 3600)
            total_removed, total_size_freed = 0, 0
            
            for folder in [self.upload_folder] + self.result_folders:
                if not os.path.exists(folder):
                    continue
                    
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            if os.path.getmtime(file_path) < cutoff_time:
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                total_removed += 1
                                total_size_freed += file_size
                        except (OSError, IOError) as e:
                            logger.warning(f"Cannot remove {file_path}: {e}")
                    
                    for dir_name in dirs:
                        try:
                            dir_path = os.path.join(root, dir_name)
                            if not os.listdir(dir_path):
                                os.rmdir(dir_path)
                        except (OSError, IOError):
                            pass
            
            if total_removed > 0:
                size_mb = total_size_freed / (1024 * 1024)
                logger.info(f"Age cleanup: {total_removed} files, {size_mb:.1f}MB freed")
                
        except Exception as e:
            logger.error(f"Age-based cleanup error: {e}")


###############################################################################
# SIZE-BASED CLEANUP  
# Enforce storage limits by removing oldest files
###############################################################################

    def _cleanup_by_size(self):
        """Size-based cleanup - O(n log n) where n is file count (due to sorting)"""
        try:
            max_size_bytes = self.max_total_size_mb * 1024 * 1024
            files_info = []
            
            for folder in [self.upload_folder] + self.result_folders:
                if not os.path.exists(folder):
                    continue
                    
                for root, _, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stat = os.stat(file_path)
                            files_info.append({
                                'path': file_path, 'size': stat.st_size, 'mtime': stat.st_mtime
                            })
                        except (OSError, IOError):
                            continue
            
            total_size = sum(f['size'] for f in files_info)
            
            if total_size <= max_size_bytes:
                return
            
            files_info.sort(key=lambda x: x['mtime'])
            
            removed_count, freed_size = 0, 0
            
            for file_info in files_info:
                if total_size - freed_size <= max_size_bytes:
                    break
                
                try:
                    os.remove(file_info['path'])
                    removed_count += 1
                    freed_size += file_info['size']
                except (OSError, IOError) as e:
                    logger.warning(f"Cannot remove {file_info['path']}: {e}")
            
            if removed_count > 0:
                freed_mb = freed_size / (1024 * 1024)
                logger.info(f"Size cleanup: {removed_count} files, {freed_mb:.1f}MB freed")
                
        except Exception as e:
            logger.error(f"Size-based cleanup error: {e}")


###############################################################################
# ORPHANED SESSION CLEANUP
# Remove files from expired sessions
###############################################################################

    def _cleanup_orphaned_sessions(self):
        """Remove files from sessions that no longer exist"""
        try:
            from security import secure_session_manager
            
            session_files = []
            session_pattern = r'session_\d{8}_\d{6}'
            
            for folder in [self.upload_folder] + self.result_folders:
                if not os.path.exists(folder):
                    continue
                    
                for root, _, files in os.walk(folder):
                    for file in files:
                        if 'session_' in file:
                            session_files.append(os.path.join(root, file))
            
            active_sessions = set()
            try:
                import re
                for file_path in session_files:
                    filename = os.path.basename(file_path)
                    match = re.search(session_pattern, filename)
                    if match:
                        session_id = match.group(0)
                        if secure_session_manager.get_session(session_id):
                            active_sessions.add(session_id)
            except Exception as e:
                logger.warning(f"Could not check active sessions: {e}")
                return
            
            removed_count = 0
            for file_path in session_files:
                try:
                    filename = os.path.basename(file_path)
                    match = re.search(session_pattern, filename)
                    if match:
                        session_id = match.group(0)
                        if session_id not in active_sessions:
                            os.remove(file_path)
                            removed_count += 1
                except Exception as e:
                    logger.warning(f"Could not remove orphaned file {file_path}: {e}")
            
            if removed_count > 0:
                logger.info(f"Orphan cleanup: Removed {removed_count} orphaned session files")
                
        except Exception as e:
            logger.error(f"Error in orphaned session cleanup: {e}")


###############################################################################
# MANUAL OPERATIONS & STATISTICS
# Admin-triggered cleanup and storage monitoring
###############################################################################

    def manual_cleanup(self) -> Dict[str, int]:
        """Manually trigger all cleanup operations"""
        logger.info("Starting manual cleanup...")
        
        stats = {'files_before': 0, 'files_after': 0, 'size_before_mb': 0, 'size_after_mb': 0}
        
        for folder in [self.upload_folder] + self.result_folders:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stats['files_before'] += 1
                            stats['size_before_mb'] += os.path.getsize(file_path)
                        except (OSError, IOError):
                            pass
        
        stats['size_before_mb'] /= (1024 * 1024)
        
        self._cleanup_old_files()
        self._cleanup_by_size()
        self._cleanup_orphaned_sessions()
        
        for folder in [self.upload_folder] + self.result_folders:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stats['files_after'] += 1
                            stats['size_after_mb'] += os.path.getsize(file_path)
                        except (OSError, IOError):
                            pass
        
        stats['size_after_mb'] /= (1024 * 1024)
        
        logger.info(f"Manual cleanup complete: {stats['files_before'] - stats['files_after']} files removed, "
                   f"{stats['size_before_mb'] - stats['size_after_mb']:.1f}MB freed")
        
        return stats

    def get_storage_stats(self) -> Dict[str, float]:
        """Get current storage statistics"""
        stats = {'total_files': 0, 'total_size_mb': 0, 'uploads_size_mb': 0, 'results_size_mb': 0}
        
        if os.path.exists(self.upload_folder):
            for root, _, files in os.walk(self.upload_folder):
                for file in files:
                    try:
                        file_size = os.path.getsize(os.path.join(root, file))
                        stats['total_files'] += 1
                        stats['total_size_mb'] += file_size
                        stats['uploads_size_mb'] += file_size
                    except (OSError, IOError):
                        pass
        
        for folder in self.result_folders:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        try:
                            file_size = os.path.getsize(os.path.join(root, file))
                            stats['total_files'] += 1
                            stats['total_size_mb'] += file_size
                            stats['results_size_mb'] += file_size
                        except (OSError, IOError):
                            pass
        
        stats['total_size_mb'] /= (1024 * 1024)
        stats['uploads_size_mb'] /= (1024 * 1024)
        stats['results_size_mb'] /= (1024 * 1024)
        
        return stats


###############################################################################
# GLOBAL INSTANCE
# Shared cleanup manager
###############################################################################

cleanup_manager = CleanupManager(
    max_age_hours=24,
    max_total_size_mb=100,
    cleanup_interval_hours=1
)