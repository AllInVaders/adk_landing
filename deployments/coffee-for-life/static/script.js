document.addEventListener('DOMContentLoaded', () => {
    const preorderForm = document.getElementById('preorderForm');
    const emailInput = document.getElementById('emailInput');
    const submitButton = document.getElementById('submitButton');
    const formMessage = document.getElementById('formMessage');
    const successModal = document.getElementById('successModal');
    const closeModal = document.getElementById('closeModal');

    if (!preorderForm || !emailInput || !submitButton || !formMessage || !successModal || !closeModal) {
        console.error('One or more required DOM elements not found.');
        return;
    }

    preorderForm.addEventListener('submit', async (event) => {
        event.preventDefault(); // Prevent default form submission

        formMessage.textContent = ''; // Clear previous messages
        formMessage.style.color = ''; // Reset color

        const email = emailInput.value.trim();

        // Basic client-side validation
        if (!email) {
            formMessage.textContent = 'Please enter your email address.';
            formMessage.style.color = 'var(--color-primary-red)';
            return;
        }

        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            formMessage.textContent = 'Please enter a valid email address.';
            formMessage.style.color = 'var(--color-primary-red)';
            return;
        }

        // Show loading state
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="loading-spinner"></span> Pre-ordering...';

        try {
            const response = await fetch('/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email: email }),
            });

            if (response.ok) {
                // Show success modal
                successModal.classList.add('visible');
                emailInput.value = ''; // Clear input field
            } else {
                const errorData = await response.json();
                formMessage.textContent = errorData.message || 'Something went wrong. Please try again.';
                formMessage.style.color = 'var(--color-primary-red)';
            }
        } catch (error) {
            console.error('Fetch error:', error);
            formMessage.textContent = 'Network error. Please check your connection and try again.';
            formMessage.style.color = 'var(--color-primary-red)';
        } finally {
            // Restore button state
            submitButton.disabled = false;
            submitButton.textContent = 'Pre-order NOW';
        }
    });

    closeModal.addEventListener('click', () => {
        successModal.classList.remove('visible');
    });

    // Close modal if clicking outside
    successModal.addEventListener('click', (event) => {
        if (event.target === successModal) {
            successModal.classList.remove('visible');
        }
    });
});