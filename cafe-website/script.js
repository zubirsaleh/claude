/* ============================================================
   Feinschmecker Cafe — Main JavaScript
   ============================================================ */

/* ---------- Navbar scroll behaviour ----------------------- */
const navbar = document.getElementById('navbar');

window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 40);
  scrollTopBtn.classList.toggle('visible', window.scrollY > 400);
});

/* ---------- Mobile menu toggle ---------------------------- */
const hamburger = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobile-menu');

hamburger.addEventListener('click', () => {
  const isOpen = mobileMenu.classList.toggle('open');
  hamburger.classList.toggle('open', isOpen);
  hamburger.setAttribute('aria-expanded', isOpen);
});

// Close mobile menu when a link is clicked
mobileMenu.querySelectorAll('a').forEach(link => {
  link.addEventListener('click', () => {
    mobileMenu.classList.remove('open');
    hamburger.classList.remove('open');
    hamburger.setAttribute('aria-expanded', false);
  });
});

/* ---------- Active nav link on scroll --------------------- */
const sections  = document.querySelectorAll('section[id]');
const navLinks  = document.querySelectorAll('.nav-links a');

const sectionObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      navLinks.forEach(a => a.classList.remove('active'));
      const active = document.querySelector(`.nav-links a[href="#${entry.target.id}"]`);
      if (active) active.classList.add('active');
    }
  });
}, { threshold: 0.45 });

sections.forEach(s => sectionObserver.observe(s));

/* ---------- Menu category tabs ---------------------------- */
const tabBtns   = document.querySelectorAll('.tab-btn');
const menuPanels = document.querySelectorAll('.menu-panel');

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;

    tabBtns.forEach(b => b.classList.remove('active'));
    menuPanels.forEach(p => p.classList.remove('active'));

    btn.classList.add('active');
    document.getElementById(`menu-${target}`)?.classList.add('active');
  });
});

/* ---------- Scroll-reveal on scroll ----------------------- */
const revealEls = document.querySelectorAll('[data-reveal]');

const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('revealed');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

revealEls.forEach(el => revealObserver.observe(el));

/* ---------- Scroll-to-top button -------------------------- */
const scrollTopBtn = document.getElementById('scroll-top');

scrollTopBtn.addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

/* ---------- Gallery lightbox (minimal) -------------------- */
const galleryItems = document.querySelectorAll('.gallery-item');

galleryItems.forEach(item => {
  item.addEventListener('click', () => {
    // When real photos are added, open a lightbox here.
    // For now this is a no-op placeholder.
  });
});

/* ---------- Smooth-scroll for all anchor links ------------ */
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', e => {
    const target = document.querySelector(anchor.getAttribute('href'));
    if (!target) return;
    e.preventDefault();
    const offset = navbar.offsetHeight + 12;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top, behavior: 'smooth' });
  });
});

/* ---------- Hero CTA — "View Menu" scrolls to menu -------- */
document.getElementById('cta-menu')?.addEventListener('click', e => {
  e.preventDefault();
  document.getElementById('menu')?.scrollIntoView({ behavior: 'smooth' });
});
