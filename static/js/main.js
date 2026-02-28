// Main JavaScript for CapstoneGuard

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-warning)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // HTMX event listeners
    document.body.addEventListener('htmx:afterSwap', function(event) {
        console.log('HTMX content swapped');
    });
    
    document.body.addEventListener('htmx:beforeRequest', function(event) {
        // Show loading indicator if needed
        const target = event.detail.target;
        if (target) {
            target.classList.add('htmx-loading');
        }
    });
    
    document.body.addEventListener('htmx:afterRequest', function(event) {
        // Hide loading indicator
        const target = event.detail.target;
        if (target) {
            target.classList.remove('htmx-loading');
        }
    });
});

// Mark notification as read
function markAsRead(notificationId) {
    fetch(`/notifications/${notificationId}/read`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const badge = document.querySelector('.badge.bg-danger');
            if (badge) {
                let count = parseInt(badge.textContent);
                count = Math.max(0, count - 1);
                if (count > 0) {
                    badge.textContent = count;
                } else {
                    badge.remove();
                }
            }
        }
    })
    .catch(error => console.error('Error:', error));
}

// Confirm before deleting
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this?');
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    });
}
