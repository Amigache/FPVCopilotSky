/**
 * Fallback fix for scrollbar layout shift in older browsers
 * Modern browsers use scrollbar-gutter: stable in CSS instead
 */

export function initScrollbarFix() {
  // Attempt to use ResizeObserver for older browsers that don't support scrollbar-gutter
  if (!window.ResizeObserver) {
    return () => {};
  }

  function adjustForLayoutShift() {
    const hasScroll = document.documentElement.scrollHeight > window.innerHeight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    
    if (hasScroll && scrollbarWidth > 0) {
      // Scrollbar visible and taking space - compensate
      document.documentElement.style.marginRight = `-${scrollbarWidth}px`;
      document.documentElement.style.paddingRight = `${scrollbarWidth}px`;
    } else {
      // Reset
      document.documentElement.style.marginRight = '0';
      document.documentElement.style.paddingRight = '0';
    }
  }

  // Monitor content size changes
  const observer = new ResizeObserver(() => {
    requestAnimationFrame(adjustForLayoutShift);
  });
  
  observer.observe(document.body);

  // Monitor resize/orientation changes
  window.addEventListener('resize', adjustForLayoutShift);
  window.addEventListener('orientationchange', () => {
    setTimeout(adjustForLayoutShift, 150);
  });

  adjustForLayoutShift();

  return () => {
    observer.disconnect();
    window.removeEventListener('resize', adjustForLayoutShift);
    window.removeEventListener('orientationchange', adjustForLayoutShift);
  };
}
