import { useRef } from 'react';
import useOnScreen from './useOnScreen';

const useReveal = (delay = 0) => {
  const ref = useRef(null);
  const isVisible = useOnScreen(ref);
  return {
    ref,
    className: `transition-all duration-1000 ease-out transform ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-12"}`,
    style: { transitionDelay: `${delay}ms` }
  };
};

export default useReveal;