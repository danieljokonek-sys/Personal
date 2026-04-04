/* ============================================================
   Daniel Okonek — Site Script
   ============================================================ */

// --- Sticky nav on scroll ---
const header = document.getElementById('header');
const hero   = document.getElementById('hero');

if (header && hero) {
  const navObserver = new IntersectionObserver(
    ([entry]) => header.classList.toggle('scrolled', !entry.isIntersecting),
    { threshold: 0.05 }
  );
  navObserver.observe(hero);
}

// --- Reveal animations on scroll ---
const revealEls = document.querySelectorAll('[data-reveal]');

if (revealEls.length) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
  );

  revealEls.forEach((el) => revealObserver.observe(el));
}

// --- Smooth scroll for anchor links ---
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener('click', function (e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth' });
    }
  });
});
