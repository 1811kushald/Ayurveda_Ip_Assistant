from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin that restricts access to admin and super_admin users."""

    def test_func(self):
        return self.request.user.is_admin


class SuperAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin that restricts access to super_admin users only."""

    def test_func(self):
        return self.request.user.is_super_admin
