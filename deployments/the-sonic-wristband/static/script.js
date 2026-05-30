
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('waitlist-form');
    const emailInput = document.getElementById('email-input');
    const submitButton = document.getElementById('submit-button');
    const successMessage = document.getElementById('success-message');

    form.addEventListener('submit', async (event) => {
        event.preventDefault(); // Prevent default form submission

        // Frontend validation
        if (!emailInput.value || !emailInput.value.includes('@')) {
            alert('Please enter a valid email address.');
            emailInput.focus();
            return;
        }

        // Toggle loading state
        submitButton.classList.add('loading');
        submitButton.setAttribute('disabled', 'true');

        const email = emailInput.value;

        try {
            const response = await fetch('/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email: email }),
            });

            if (response.ok) {
                // Success!
                form.classList.add('hidden'); // Hide the form
                successMessage.classList.remove('hidden'); // Make sure it's not display: none
                successMessage.classList.add('visible'); // Show success message with animation
                emailInput.value = ''; // Clear input
            } else {
                // Handle server errors or non-200 responses
                const errorData = await response.json();
                console.error('Server error:', errorData);
                alert(`Failed to sign up: ${errorData.message || 'Please try again later.'}`);
            }
        } catch (error) {
            console.error('Network or fetch error:', error);
            alert('An unexpected error occurred. Please check your internet connection and try again.');
        } finally {
            // Revert loading state
            submitButton.classList.remove('loading');
            submitButton.removeAttribute('disabled');
        }
    });

    // Simple visibility toggle for success message (for initial hidden state)
    // No need for a separate class for 'display: none', just control 'visible' class
    // via JS to leverage CSS transition. Initial state is 'hidden' in HTML.
});
