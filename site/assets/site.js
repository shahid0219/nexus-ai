// NEXUS AI project site - small, dependency-free enhancements.
(function () {
  'use strict'

  // Sticky nav border once the page scrolls.
  var nav = document.getElementById('nav')
  var onScroll = function () {
    if (window.scrollY > 8) nav.classList.add('scrolled')
    else nav.classList.remove('scrolled')
  }
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()

  // Mobile navigation.
  var toggle = document.getElementById('navToggle')
  var links = document.getElementById('navLinks')
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open')
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false')
    })
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        links.classList.remove('open')
        toggle.setAttribute('aria-expanded', 'false')
      }
    })
  }

  // Install tabs.
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'))
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      tabs.forEach(function (t) {
        t.classList.remove('active')
        t.setAttribute('aria-selected', 'false')
      })
      tab.classList.add('active')
      tab.setAttribute('aria-selected', 'true')
      Array.prototype.forEach.call(document.querySelectorAll('.pane'), function (p) {
        p.classList.remove('active')
      })
      var pane = document.getElementById(tab.getAttribute('aria-controls'))
      if (pane) pane.classList.add('active')
    })
  })

  // Reveal on scroll, respecting reduced motion.
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  var items = document.querySelectorAll('.reveal')
  if (reduce || !('IntersectionObserver' in window)) {
    Array.prototype.forEach.call(items, function (el) { el.classList.add('in') })
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in')
          io.unobserve(entry.target)
        }
      })
    }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 })
    Array.prototype.forEach.call(items, function (el) { io.observe(el) })
  }
})()
