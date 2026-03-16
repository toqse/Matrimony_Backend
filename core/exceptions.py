"""
Custom exception handler for consistent API error responses.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        custom = {
            'success': False,
            'error': {
                'code': response.status_code,
                'message': _get_error_message(response.data),
                'details': response.data,
            },
        }
        response.data = custom
    else:
        custom = {
            'success': False,
            'error': {
                'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': str(exc),
                'details': None,
            },
        }
        response = Response(custom, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return response


def _get_error_message(data):
    if isinstance(data, dict):
        if 'detail' in data:
            d = data['detail']
            return d[0] if isinstance(d, list) and d else d
        for key in ['message', 'error', 'non_field_errors']:
            if key in data:
                val = data[key]
                return val[0] if isinstance(val, list) and val else val
        for v in data.values():
            if v:
                return v[0] if isinstance(v, list) and v else v
        return 'Validation error'
    if isinstance(data, list):
        return data[0] if data else 'Error'
    return str(data)
