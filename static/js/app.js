// app.js
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('gizleBtn');
    const parag = document.querySelector('main p');

    btn.addEventListener('click', () => {
        parag.style.display = (parag.style.display === 'none') ? 'block' : 'none';
    });
});