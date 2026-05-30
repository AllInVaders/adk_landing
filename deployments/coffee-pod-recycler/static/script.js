
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('waitlist-form');
    const emailInput = document.getElementById('email-input');
    const formMessage = document.getElementById('form-message');

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const email = emailInput.value;
        if (!email) {
            showMessage('Please enter your email address.', 'error');
            return;
        }

        showMessage('Submitting...', 'loading');
        emailInput.disabled = true;
        form.querySelector('button').disabled = true;

        try {
            const response = await fetch('/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email: email }),
            });

            if (response.ok) {
                showMessage("Success! You've joined the waitlist!", 'success');
                emailInput.value = ''; // Clear input on success
            } else {
                const errorData = await response.json();
                showMessage(errorData.message || 'Something went wrong. Please try again.', 'error');
            }
        } catch (error) {
            console.error('Submission error:', error);
            showMessage('Network error. Please check your connection and try again.', 'error');
        } finally {
            emailInput.disabled = false;
            form.querySelector('button').disabled = false;
        }
    });

    function showMessage(message, type) {
        formMessage.textContent = message;
        formMessage.className = 'form-message show'; // Reset classes
        if (type === 'success') {
            formMessage.classList.add('success');
        } else if (type === 'error') {
            formMessage.classList.add('error');
        } else if (type === 'loading') {
            formMessage.classList.add('loading');
            // Add a simple loading animation, e.g., pulsating text or dots
            let dots = 0;
            const loadingInterval = setInterval(() => {
                dots = (dots % 3) + 1;
                formMessage.textContent = message + '.'.repeat(dots);
            }, 500);
            formMessage.dataset.loadingInterval = loadingInterval; // Store interval ID
        }

        if (type !== 'loading' && formMessage.dataset.loadingInterval) {
            clearInterval(parseInt(formMessage.dataset.loadingInterval));
            delete formMessage.dataset.loadingInterval;
        }
    }
});
