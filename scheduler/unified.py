"""Unified Scheduler for Content Machine multi-platform publishing."""
import asyncio
from datetime import datetime
from typing import Optional
from core.shared.base import PlatformType
from core.shared.loader import PlatformLoader
from scheduler.models import PlatformTask, TaskStatus, TaskSchedule, DailyPlan
from scheduler.strategies import PublisherStrategy, FacebookPublisher, LinkedInPublisher, TwitterPublisher


class UnifiedScheduler:
    """Unified scheduler for all platforms.
    
    Uses Strategy pattern for different platform publishers.
    Manages task scheduling, execution, and retries.
    """
    
    def __init__(self, config=None):
        self.config = config
        self.platforms = {}
        self.strategies = {}
        self.task_queue = asyncio.Queue()
        self._worker_task = None
        self._stop_event = asyncio.Event()
        self._schedule_pending = []
        # topic_id -> PlatformTask (in-memory registry for topic-driven tasks)
        self._topic_tasks = {}
        # set of topic ids marked as cancelled/deleted
        self._canceled_topic_ids = set()
        # background sync task for pending topic changes
        self._sync_task = None
        # seconds between polling pending_topic_changes.json
        self.sync_interval = 5
    
    async def initialize(self):
        """Initialize all platform publishers."""
        from orchestrator import OrchestratorConfig
        
        orchestrator_config = self.config or OrchestratorConfig.from_env()
        
        platform_configs = {
            PlatformType.FACEBOOK: orchestrator_config.facebook_config,
            PlatformType.LINKEDIN: orchestrator_config.linkedin_config,
            PlatformType.TWITTER: orchestrator_config.twitter_config,
        }
        
        for platform_type, platform_config in platform_configs.items():
            if platform_config:
                try:
                    platform = PlatformLoader.load_platform(platform_type, platform_config)
                    self.platforms[platform_type] = platform
                    
                    strategy = self._create_strategy(platform_type, platform)
                    self.strategies[platform_type] = strategy
                except Exception as e:
                    print(f"Failed to load {platform_type.value}: {e}")
    
    def _create_strategy(self, platform_type, platform):
        """Factory method to create platform strategy."""
        strategies_map = {
            PlatformType.FACEBOOK: FacebookPublisher,
            PlatformType.LINKEDIN: LinkedInPublisher,
            PlatformType.TWITTER: TwitterPublisher,
        }
        strategy_class = strategies_map.get(platform_type)
        if strategy_class:
            return strategy_class(platform)
        raise ValueError(f"No strategy for {platform_type}")
    
    async def add_task(self, task: PlatformTask):
        """Add a task to the queue."""
        await self.task_queue.put(task)
    
    async def add_daily_plan(self, plan: DailyPlan):
        """Add all tasks from a daily plan."""
        for task in plan.get_tasks():
            await self.add_task(task)
    
    async def schedule_task(self, task: PlatformTask, schedule: TaskSchedule):
        """Schedule a task for a specific time."""
        task.schedule = schedule
        self._schedule_pending.append((task, schedule))
    
    async def execute_task(self, task: PlatformTask):
        """Execute a single task."""
        # honor cancellation requests propagated from topic-sync
        if getattr(self, "_canceled_topic_ids", None) and task.id in self._canceled_topic_ids:
            task.status = TaskStatus.CANCELLED
            return

        if task.platform not in self.strategies:
            task.status = TaskStatus.FAILED
            task.result.error = f"No strategy for {task.platform}"
            return
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        strategy = self.strategies[task.platform]
        result = await strategy.publish_task(task)
        
        if result.success:
            task.status = TaskStatus.COMPLETED
            task.result = result
        else:
            task.retries += 1
            if task.retries < task.max_retries:
                task.status = TaskStatus.PENDING
                await asyncio.sleep(60 * (2 ** task.retries))
                await strategy.publish_task(task)
            else:
                task.status = TaskStatus.FAILED
                task.result = result
        
        task.completed_at = datetime.now()
        task.updated_at = datetime.now()
    
    async def _worker(self):
        """Worker coroutine that processes the queue."""
        while not self._stop_event.is_set():
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                asyncio.create_task(self.execute_task(task))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Worker error: {e}")
    
    async def start(self):
        """Start the scheduler."""
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker())
        # start background sync loop
        self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def stop(self):
        """Stop the scheduler."""
        self._stop_event.set()
        # wait for sync and worker tasks to finish
        if self._sync_task:
            await self._sync_task
        if self._worker_task:
            await self._worker_task
    
    async def run_once(self) -> list:
        """Run all pending tasks once (non-scheduled)."""
        tasks = []
        while not self.task_queue.empty():
            task = await self.task_queue.get()
            tasks.append(task)
            asyncio.create_task(self.execute_task(task))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return tasks

    async def sync_pending_topic_changes(self) -> list:
        """Consume pending_topic_changes.json and apply changes to scheduler tasks."""
        import json
        try:
            from scheduler.topic_sync import PENDING_FILE
        except Exception:
            return []

        if not PENDING_FILE.exists():
            return []

        try:
            raw = json.loads(PENDING_FILE.read_text(encoding='utf-8') or "[]")
        except Exception:
            raw = []

        # best-effort: clear the pending file to avoid re-processing
        try:
            PENDING_FILE.write_text(json.dumps([], ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

        processed = []
        from scheduler.models import PlatformTask, TaskSchedule
        from core.shared.base import PlatformType
        from common.utils.smart_scheduler import get_free_hour
        for entry in raw:
            action = entry.get('action')
            topic_obj = entry.get('topic') or {}
            tid = topic_obj.get('id')
            platform_str = topic_obj.get('platform')
            try:
                platform = PlatformType(platform_str) if platform_str else None
            except Exception:
                platform = None

            account_id = topic_obj.get('account_id')
            raw_data = topic_obj.get('raw') or {}
            topic_text = raw_data.get('topic') or topic_obj.get('topic') or ''
            persona = topic_obj.get('persona') or raw_data.get('persona') or 'default'

            if action == 'create':
                task = PlatformTask()
                if tid:
                    task.id = tid
                if platform:
                    task.platform = platform
                task.persona = persona
                task.topic = topic_text
                task.metadata = {'account_id': account_id, 'source': topic_obj.get('source'), 'raw': raw_data}
                # map date_prevue to schedule if present
                date_prevue = raw_data.get('date_prevue') or topic_obj.get('date_prevue')
                if date_prevue:
                    try:
                        dt = datetime.fromisoformat(date_prevue)
                        task.scheduled_at = dt
                        task.schedule = TaskSchedule(hour=dt.hour, minute=dt.minute)
                        # ask SmartScheduler for a free hour to avoid conflicts
                        try:
                            free_h = get_free_hour(platform.value, preferred_hour=task.schedule.hour, account_id=account_id)
                            task.schedule.hour = free_h
                        except Exception:
                            pass
                    except Exception:
                        pass

                self._topic_tasks[task.id] = task
                await self.add_task(task)
                processed.append({'action': 'create', 'id': task.id})

            elif action == 'update':
                existing = self._topic_tasks.get(tid)
                if existing:
                    existing.topic = topic_text or existing.topic
                    existing.persona = persona or existing.persona
                    existing.metadata.update({'raw': raw_data, 'source': topic_obj.get('source'), 'account_id': account_id})
                    existing.updated_at = datetime.now()
                    processed.append({'action': 'update', 'id': tid})
                else:
                    # fallback to create
                    task = PlatformTask()
                    if tid:
                        task.id = tid
                    if platform:
                        task.platform = platform
                    task.persona = persona
                    task.topic = topic_text
                    task.metadata = {'account_id': account_id, 'source': topic_obj.get('source'), 'raw': raw_data}
                    self._topic_tasks[task.id] = task
                    await self.add_task(task)
                    processed.append({'action': 'create_from_update', 'id': task.id})

            elif action == 'delete':
                if tid in self._topic_tasks:
                    self._canceled_topic_ids.add(tid)
                    t = self._topic_tasks[tid]
                    t.status = TaskStatus.CANCELLED
                    t.metadata['deleted'] = True
                    processed.append({'action': 'delete', 'id': tid})
                else:
                    # mark canceled globally to prevent later execution
                    self._canceled_topic_ids.add(tid)
                    processed.append({'action': 'delete_unknown', 'id': tid})

        return processed

    async def _sync_loop(self):
        """Background loop that polls pending_topic_changes.json and applies changes."""
        while not self._stop_event.is_set():
            try:
                processed = await self.sync_pending_topic_changes()
                if processed:
                    print(f"[UnifiedScheduler] synced {len(processed)} pending topic changes")
            except Exception as e:
                print(f"[UnifiedScheduler] sync loop error: {e}")

            # wait for either stop event or timeout
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.sync_interval)
            except asyncio.TimeoutError:
                # timeout expired, loop again
                continue


async def create_scheduler(config=None):
    """Create and initialize a scheduler."""
    scheduler = UnifiedScheduler(config)
    await scheduler.initialize()
    return scheduler