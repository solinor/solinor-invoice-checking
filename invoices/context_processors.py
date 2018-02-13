from invoices.models import TenkfUser


def add_tenkfuser(request):
    if request.user and request.user.id is not None:  # user.id is None for anonymous user
        try:
            return {
                "tenkf_user": TenkfUser.objects.get(email=request.user.email)
            }
        except TenkfUser.DoesNotExist:
            pass
    return {}
