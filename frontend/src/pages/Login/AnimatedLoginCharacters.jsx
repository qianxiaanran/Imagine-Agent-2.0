import React, { memo, useEffect, useRef, useState } from 'react';

const Pupil = memo(function Pupil({ size = 12, pupilColor = 'black', offsetX = 0, offsetY = 0 }) {
  return (
    <div
      className="rounded-full transition-transform duration-100 ease-out"
      style={{
        width: `${size}px`,
        height: `${size}px`,
        backgroundColor: pupilColor,
        transform: `translate(${offsetX}px, ${offsetY}px)`,
        willChange: 'transform',
      }}
    />
  );
});

const EyeBall = memo(function EyeBall({
  size = 48,
  pupilSize = 16,
  eyeColor = 'white',
  pupilColor = 'black',
  isBlinking = false,
  offsetX = 0,
  offsetY = 0,
}) {
  return (
    <div
      className="flex items-center justify-center rounded-full transition-all duration-150"
      style={{
        width: `${size}px`,
        height: isBlinking ? '2px' : `${size}px`,
        backgroundColor: eyeColor,
        overflow: 'hidden',
        willChange: 'transform, height',
      }}
    >
      {!isBlinking && (
        <div
          className="rounded-full transition-transform duration-100 ease-out"
          style={{
            width: `${pupilSize}px`,
            height: `${pupilSize}px`,
            backgroundColor: pupilColor,
            transform: `translate(${offsetX}px, ${offsetY}px)`,
            willChange: 'transform',
          }}
        />
      )}
    </div>
  );
});

const DEFAULT_RECT = { left: 0, top: 0, width: 480, height: 360 };
const DEFAULT_LOOK = { faceX: 0, faceY: 0, bodySkew: 0 };

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const calculateLook = (
  mouse,
  rect,
  centerX,
  centerY,
  { maxX, maxY, bodyDivisor = 120, faceDivisorX = 20, faceDivisorY = 30 }
) => {
  if (!mouse) return DEFAULT_LOOK;

  const absoluteX = rect.left + centerX;
  const absoluteY = rect.top + centerY;
  const deltaX = mouse.x - absoluteX;
  const deltaY = mouse.y - absoluteY;

  return {
    faceX: clamp(deltaX / faceDivisorX, -maxX, maxX),
    faceY: clamp(deltaY / faceDivisorY, -maxY, maxY),
    bodySkew: clamp(-deltaX / bodyDivisor, -6, 6),
  };
};

const setNodeStyles = (node, styles) => {
  if (!node) return;
  Object.entries(styles).forEach(([key, value]) => {
    node.style[key] = value;
  });
};

const AnimatedLoginCharacters = memo(function AnimatedLoginCharacters({
  isTyping = false,
  showPassword = false,
  passwordLength = 0,
  reducedMotion = false,
}) {
  const containerRef = useRef(null);
  const purpleBodyRef = useRef(null);
  const purpleEyesRef = useRef(null);
  const blackBodyRef = useRef(null);
  const blackEyesRef = useRef(null);
  const orangeBodyRef = useRef(null);
  const orangeEyesRef = useRef(null);
  const yellowBodyRef = useRef(null);
  const yellowEyesRef = useRef(null);
  const yellowMouthRef = useRef(null);
  const rectRef = useRef(DEFAULT_RECT);
  const mouseRef = useRef(null);
  const pendingMouseRef = useRef(null);
  const frameRef = useRef(0);
  const [isPurpleBlinking, setIsPurpleBlinking] = useState(false);
  const [isBlackBlinking, setIsBlackBlinking] = useState(false);
  const [isPurplePeeking, setIsPurplePeeking] = useState(false);

  const motionEnabled = !reducedMotion;

  const applyScene = () => {
    const rect = rectRef.current;
    const mouse = mouseRef.current;
    const purplePos = motionEnabled
      ? calculateLook(mouse, rect, rect.width * 0.28, rect.height * 0.3, { maxX: 15, maxY: 10 })
      : DEFAULT_LOOK;
    const blackPos = motionEnabled
      ? calculateLook(mouse, rect, rect.width * 0.57, rect.height * 0.28, { maxX: 12, maxY: 8 })
      : DEFAULT_LOOK;
    const yellowPos = motionEnabled
      ? calculateLook(mouse, rect, rect.width * 0.77, rect.height * 0.24, { maxX: 14, maxY: 10 })
      : DEFAULT_LOOK;
    const orangePos = motionEnabled
      ? calculateLook(mouse, rect, rect.width * 0.21, rect.height * 0.52, { maxX: 14, maxY: 10 })
      : DEFAULT_LOOK;

    const isHidingPassword = passwordLength > 0 && !showPassword;
    const shouldLookAtEachOther = isTyping;
    const shouldPurplePeek = motionEnabled && passwordLength > 0 && showPassword && isPurplePeeking;

    const purpleTransform = (passwordLength > 0 && showPassword)
      ? 'skewX(0deg)'
      : (isTyping || isHidingPassword)
        ? `skewX(${purplePos.bodySkew - 12}deg) translateX(40px)`
        : `skewX(${purplePos.bodySkew}deg)`;
    const blackTransform = (passwordLength > 0 && showPassword)
      ? 'skewX(0deg)'
      : shouldLookAtEachOther
        ? `skewX(${blackPos.bodySkew * 1.5 + 10}deg) translateX(20px)`
        : (isTyping || isHidingPassword)
          ? `skewX(${blackPos.bodySkew * 1.5}deg)`
          : `skewX(${blackPos.bodySkew}deg)`;
    const orangeTransform = (passwordLength > 0 && showPassword) ? 'skewX(0deg)' : `skewX(${orangePos.bodySkew}deg)`;
    const yellowTransform = (passwordLength > 0 && showPassword) ? 'skewX(0deg)' : `skewX(${yellowPos.bodySkew}deg)`;

    setNodeStyles(purpleBodyRef.current, {
      height: `${(isTyping || isHidingPassword) ? 400 : 360}px`,
      transform: purpleTransform,
    });
    setNodeStyles(purpleEyesRef.current, {
      left: (passwordLength > 0 && showPassword) ? '20px' : shouldLookAtEachOther ? '55px' : `${45 + purplePos.faceX}px`,
      top: (passwordLength > 0 && showPassword) ? '35px' : shouldLookAtEachOther ? '65px' : `${40 + purplePos.faceY}px`,
    });

    setNodeStyles(blackBodyRef.current, { transform: blackTransform });
    setNodeStyles(blackEyesRef.current, {
      left: (passwordLength > 0 && showPassword) ? '10px' : shouldLookAtEachOther ? '32px' : `${26 + blackPos.faceX}px`,
      top: (passwordLength > 0 && showPassword) ? '28px' : shouldLookAtEachOther ? '12px' : `${32 + blackPos.faceY}px`,
    });

    setNodeStyles(orangeBodyRef.current, { transform: orangeTransform });
    setNodeStyles(orangeEyesRef.current, {
      left: (passwordLength > 0 && showPassword) ? '50px' : `${82 + orangePos.faceX}px`,
      top: (passwordLength > 0 && showPassword) ? '78px' : `${84 + orangePos.faceY}px`,
    });

    setNodeStyles(yellowBodyRef.current, { transform: yellowTransform });
    setNodeStyles(yellowEyesRef.current, {
      left: (passwordLength > 0 && showPassword) ? '20px' : `${52 + yellowPos.faceX}px`,
      top: (passwordLength > 0 && showPassword) ? '35px' : `${40 + yellowPos.faceY}px`,
    });
    setNodeStyles(yellowMouthRef.current, {
      left: (passwordLength > 0 && showPassword) ? '10px' : `${40 + yellowPos.faceX}px`,
      top: (passwordLength > 0 && showPassword) ? '88px' : `${88 + yellowPos.faceY}px`,
    });
  };

  const scheduleSceneApply = () => {
    if (frameRef.current) return;

    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = 0;
      if (pendingMouseRef.current) {
        mouseRef.current = pendingMouseRef.current;
      }
      applyScene();
    });
  };

  useEffect(() => {
    if (motionEnabled) return;
    setIsPurpleBlinking(false);
    setIsBlackBlinking(false);
    setIsPurplePeeking(false);
  }, [motionEnabled]);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const element = containerRef.current;

    const measure = () => {
      const next = element.getBoundingClientRect();
      rectRef.current = {
        left: Math.round(next.left),
        top: Math.round(next.top),
        width: Math.round(next.width),
        height: Math.round(next.height),
      };
      applyScene();
    };

    measure();
    window.addEventListener('resize', measure, { passive: true });

    let observer;
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(measure);
      observer.observe(element);
    }

    return () => {
      window.removeEventListener('resize', measure);
      observer?.disconnect();
    };
  }, []);

  useEffect(() => {
    applyScene();
  }, [isTyping, showPassword, passwordLength, isPurplePeeking, motionEnabled]);

  useEffect(() => {
    if (!motionEnabled) return undefined;

    const handlePointerMove = (event) => {
      const nextMouse = { x: event.clientX, y: event.clientY };
      const previousMouse = pendingMouseRef.current || mouseRef.current;
      if (
        previousMouse &&
        Math.abs(previousMouse.x - nextMouse.x) < 4 &&
        Math.abs(previousMouse.y - nextMouse.y) < 4
      ) {
        return;
      }

      pendingMouseRef.current = nextMouse;
      scheduleSceneApply();
    };

    window.addEventListener('pointermove', handlePointerMove, { passive: true });

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      if (frameRef.current) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = 0;
      }
    };
  }, [motionEnabled]);

  useEffect(() => {
    if (!motionEnabled) return undefined;

    const getRandomBlinkInterval = () => Math.random() * 4000 + 3000;
    let blinkTimeout = null;
    let blinkWindowTimeout = null;

    const scheduleBlink = () => {
      blinkTimeout = setTimeout(() => {
        setIsPurpleBlinking(true);
        blinkWindowTimeout = setTimeout(() => {
          setIsPurpleBlinking(false);
          scheduleBlink();
        }, 150);
      }, getRandomBlinkInterval());
    };

    scheduleBlink();

    return () => {
      if (blinkTimeout) clearTimeout(blinkTimeout);
      if (blinkWindowTimeout) clearTimeout(blinkWindowTimeout);
    };
  }, [motionEnabled]);

  useEffect(() => {
    if (!motionEnabled) return undefined;

    const getRandomBlinkInterval = () => Math.random() * 4000 + 3000;
    let blinkTimeout = null;
    let blinkWindowTimeout = null;

    const scheduleBlink = () => {
      blinkTimeout = setTimeout(() => {
        setIsBlackBlinking(true);
        blinkWindowTimeout = setTimeout(() => {
          setIsBlackBlinking(false);
          scheduleBlink();
        }, 150);
      }, getRandomBlinkInterval());
    };

    scheduleBlink();

    return () => {
      if (blinkTimeout) clearTimeout(blinkTimeout);
      if (blinkWindowTimeout) clearTimeout(blinkWindowTimeout);
    };
  }, [motionEnabled]);

  useEffect(() => {
    const shouldEnablePurplePeeking = motionEnabled && passwordLength > 0 && showPassword;
    if (!shouldEnablePurplePeeking) return undefined;

    let peekTimeout = null;
    let hideTimeout = null;

    const schedulePeek = () => {
      peekTimeout = setTimeout(() => {
        setIsPurplePeeking(true);
        hideTimeout = setTimeout(() => {
          setIsPurplePeeking(false);
          schedulePeek();
        }, 800);
      }, Math.random() * 3000 + 2000);
    };

    schedulePeek();

    return () => {
      if (peekTimeout) clearTimeout(peekTimeout);
      if (hideTimeout) clearTimeout(hideTimeout);
    };
  }, [motionEnabled, passwordLength, showPassword]);

  const transitionClassName = motionEnabled ? 'transition-all duration-300 ease-out' : '';
  const fineTransitionClassName = motionEnabled ? 'transition-all duration-180 ease-out' : '';
  const isShowingPassword = passwordLength > 0 && showPassword;
  const isTypingOrHiding = isTyping || (passwordLength > 0 && !showPassword);
  const shouldPurplePeek = motionEnabled && isShowingPassword && isPurplePeeking;

  return (
    <div
      ref={containerRef}
      className="relative h-[360px] w-[480px]"
      style={{ contain: 'layout paint style' }}
    >
      <div
        ref={purpleBodyRef}
        className={`absolute bottom-0 ${transitionClassName}`.trim()}
        style={{
          left: '64px',
          width: '160px',
          height: `${isTypingOrHiding ? 400 : 360}px`,
          backgroundColor: '#6C3FF5',
          borderRadius: '10px 10px 0 0',
          zIndex: 1,
          transform: 'skewX(0deg)',
          transformOrigin: 'bottom center',
          willChange: 'transform, height',
        }}
      >
        <div
          ref={purpleEyesRef}
          className={`absolute flex gap-8 ${transitionClassName}`.trim()}
          style={{ left: '45px', top: '40px', willChange: 'transform, left, top' }}
        >
          {[0, 1].map((item) => (
            <EyeBall
              key={`purple-eye-${item}`}
              size={18}
              pupilSize={7}
              eyeColor="white"
              pupilColor="#2D2D2D"
              isBlinking={isPurpleBlinking}
              offsetX={isShowingPassword ? (shouldPurplePeek ? 4 : -4) : isTyping ? 3 : 0}
              offsetY={isShowingPassword ? (shouldPurplePeek ? 5 : -4) : isTyping ? 4 : 0}
            />
          ))}
        </div>
      </div>

      <div
        ref={blackBodyRef}
        className={`absolute bottom-0 ${transitionClassName}`.trim()}
        style={{
          left: '220px',
          width: '112px',
          height: '290px',
          backgroundColor: '#2D2D2D',
          borderRadius: '8px 8px 0 0',
          zIndex: 2,
          transform: 'skewX(0deg)',
          transformOrigin: 'bottom center',
          willChange: 'transform',
        }}
      >
        <div
          ref={blackEyesRef}
          className={`absolute flex gap-6 ${transitionClassName}`.trim()}
          style={{ left: '26px', top: '32px', willChange: 'transform, left, top' }}
        >
          {[0, 1].map((item) => (
            <EyeBall
              key={`black-eye-${item}`}
              size={16}
              pupilSize={6}
              eyeColor="white"
              pupilColor="#2D2D2D"
              isBlinking={isBlackBlinking}
              offsetX={isShowingPassword ? -4 : 0}
              offsetY={isShowingPassword ? -4 : isTyping ? -4 : 0}
            />
          ))}
        </div>
      </div>

      <div
        ref={orangeBodyRef}
        className={`absolute bottom-0 ${transitionClassName}`.trim()}
        style={{
          left: '0px',
          width: '220px',
          height: '184px',
          zIndex: 3,
          backgroundColor: '#FF9B6B',
          borderRadius: '110px 110px 0 0',
          transform: 'skewX(0deg)',
          transformOrigin: 'bottom center',
          willChange: 'transform',
        }}
      >
        <div
          ref={orangeEyesRef}
          className={`absolute flex gap-8 ${fineTransitionClassName}`.trim()}
          style={{ left: '82px', top: '84px', willChange: 'transform, left, top' }}
        >
          {[0, 1].map((item) => (
            <Pupil
              key={`orange-eye-${item}`}
              size={12}
              pupilColor="#2D2D2D"
              offsetX={isShowingPassword ? -5 : 0}
              offsetY={isShowingPassword ? -4 : 0}
            />
          ))}
        </div>
      </div>

      <div
        ref={yellowBodyRef}
        className={`absolute bottom-0 ${transitionClassName}`.trim()}
        style={{
          left: '292px',
          width: '128px',
          height: '212px',
          backgroundColor: '#E8D754',
          borderRadius: '64px 64px 0 0',
          zIndex: 4,
          transform: 'skewX(0deg)',
          transformOrigin: 'bottom center',
          willChange: 'transform',
        }}
      >
        <div
          ref={yellowEyesRef}
          className={`absolute flex gap-6 ${fineTransitionClassName}`.trim()}
          style={{ left: '52px', top: '40px', willChange: 'transform, left, top' }}
        >
          {[0, 1].map((item) => (
            <Pupil
              key={`yellow-eye-${item}`}
              size={12}
              pupilColor="#2D2D2D"
              offsetX={isShowingPassword ? -5 : 0}
              offsetY={isShowingPassword ? -4 : 0}
            />
          ))}
        </div>
        <div
          ref={yellowMouthRef}
          className={`absolute h-[4px] w-20 rounded-full bg-[#2D2D2D] ${fineTransitionClassName}`.trim()}
          style={{ left: '40px', top: '88px', willChange: 'transform, left, top' }}
        />
      </div>
    </div>
  );
});

export default AnimatedLoginCharacters;
