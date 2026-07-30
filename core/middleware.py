"""
First-in-chain short-circuit for liveness probes.

If WSGI already handled /health/live/, this never runs for that path.
Kept as defense-in-depth when another entrypoint (e.g. Daphne) serves HTTP.
"""
from django.http import JsonResponse


class HealthLiveShortCircuitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        if path == '/health/live/' or path == '/health/live':
            return JsonResponse({'status': 'alive', 'via': 'middleware'}, status=200)
        return self.get_response(request)
