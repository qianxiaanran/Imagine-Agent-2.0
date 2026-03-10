import { useState, useEffect } from 'react';

const useOnScreen = (ref, rootMargin = "0px") => {
  const [isIntersecting, setIntersecting] = useState(false);
  useEffect(() => {
    const element = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIntersecting(true);
          observer.unobserve(entry.target);
        }
      }, { rootMargin, threshold: 0.1 }
    );
    if (element) observer.observe(element);
    return () => { if (element) observer.unobserve(element); };
  }, [ref, rootMargin]);
  return isIntersecting;
};

export default useOnScreen;
