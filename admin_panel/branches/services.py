from .models import Branch

def generate_branch_code(city):
    prefix = city[:3].upper()

    last_branch = Branch.objects.filter(code__startswith=prefix).order_by('-id').first()

    if last_branch:
        last_number = int(last_branch.code.split('-')[1])
        new_number = last_number + 1
    else:
        new_number = 1

    return f"{prefix}-{str(new_number).zfill(2)}"