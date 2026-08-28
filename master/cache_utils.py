"""
Redis cache helpers for public master lists and app config.
Short TTL + pattern invalidation on writes (signals / admin saves).
"""
from django.core.cache import cache

MASTER_CACHE_TTL = 300  # 5 minutes
MASTER_KEY_PREFIX = 'master:list:v1:'
APP_CONFIG_PUBLIC_KEY = 'app_config:public:v1'
APP_CONFIG_TTL = 300

# resource name -> used in cache keys and invalidation
RESOURCE_COUNTRIES = 'countries'
RESOURCE_STATES = 'states'
RESOURCE_DISTRICTS = 'districts'
RESOURCE_CITIES = 'cities'
RESOURCE_RELIGIONS = 'religions'
RESOURCE_CASTES = 'castes'
RESOURCE_MOTHER_TONGUES = 'mother-tongues'
RESOURCE_HEIGHTS = 'heights'
RESOURCE_MARITAL_STATUSES = 'marital-statuses-v2'
RESOURCE_COMPLEXIONS = 'complexions'
RESOURCE_INCOME_RANGES = 'income-ranges'
RESOURCE_EDUCATIONS = 'educations'
RESOURCE_EDUCATION_SUBJECTS = 'education-subjects'
RESOURCE_OCCUPATIONS = 'occupations'
RESOURCE_EMPLOYMENT_STATUSES = 'employment-statuses'
RESOURCE_MATCH_FILTERS = 'match-filters-v2'


def master_list_cache_key(resource: str, query_string: str) -> str:
    return f'{MASTER_KEY_PREFIX}{resource}:{query_string or ""}'


def get_cached_master_list(resource: str, query_string: str):
    return cache.get(master_list_cache_key(resource, query_string))


def set_cached_master_list(resource: str, query_string: str, data, ttl=MASTER_CACHE_TTL):
    cache.set(master_list_cache_key(resource, query_string), data, ttl)


def invalidate_master_resource(resource: str):
    """Delete all cached pages/filters for a master resource."""
    pattern = f'{MASTER_KEY_PREFIX}{resource}:*'
    try:
        cache.delete_pattern(pattern)
    except Exception:
        # LocMemCache / backends without delete_pattern: best-effort no-op
        pass


def invalidate_master_resources(*resources: str):
    for resource in resources:
        invalidate_master_resource(resource)


def get_cached_app_config():
    return cache.get(APP_CONFIG_PUBLIC_KEY)


def set_cached_app_config(data, ttl=APP_CONFIG_TTL):
    cache.set(APP_CONFIG_PUBLIC_KEY, data, ttl)


def invalidate_app_config():
    cache.delete(APP_CONFIG_PUBLIC_KEY)
