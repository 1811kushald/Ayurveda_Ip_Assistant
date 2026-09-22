/* IP-SAKTI Sahayak — Main JavaScript */

// HTMX configuration
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Include CSRF token in all HTMX requests
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
    if (csrfToken) {
        evt.detail.headers['X-CSRFToken'] = csrfToken;
    }
});

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });
});
