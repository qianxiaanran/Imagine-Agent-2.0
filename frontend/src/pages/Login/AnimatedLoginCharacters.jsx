import React, { useEffect, useRef, useState } from 'react';

const Pupil = ({ size = 12, pupilColor = 'black', offsetX = 0, offsetY = 0 }) => (
  <div
    className="rounded-full transition-transform duration-100 ease-out"
    style={{
      width: `${size}px`,
      height: `${size}px`,
      backgroundColor: pupilColor,
      transform: `translate(${offsetX}px, ${offsetY}px)`,
    }}
  />
);

const EyeBall = ({
  size = 48,
  pupilSize = 16,
  eyeColor = 'white',
  pupilColor = 'black',
  isBlinking = false,
  offsetX = 0,
  offsetY = 0,
}) => (
  <div
    className="flex items-center justify-center rounded-full transition-all duration-150"
    style={{
      width: `${size}px`,
      height: isBlinking ? '2px' : `${size}px`,
      backgroundColor: eyeColor,
      overflow: 'hidden',
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
        }}
      />
    )}
  </div>
);

const DEFAULT_RECT = { left: 0, top: 0, width: 480, height: 360 };

const AnimatedLoginCharacters = ({
  isTyping = false,
  showPassword = false,
  passwordLength = 0,
}) => {
  const containerRef = useRef(null);
  const [mouse, setMouse] = useState({ x: 0, y: 0 });
  const [rect, setRect] = useState(DEFAULT_RECT);
  const [isPurpleBlinking, setIsPurpleBlinking] = useState(false);
  const [isBlackBlinking, setIsBlackBlinking] = useState(false);
  const [isPurplePeeking, setIsPurplePeeking] = useState(false);

  useEffect(() => {
    const handleMouseMove = (event) => {
      setMouse({ x: event.clientX, y: event.clientY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const element = containerRef.current;

    const measure = () => {
      const next = element.getBoundingClientRect();
      setRect({
        left: next.left,
        top: next.top,
        width: next.width,
        height: next.height,
      });
    };

    measure();
    window.addEventListener('resize', measure);

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
  }, []);

  useEffect(() => {
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
  }, []);

  const shouldEnablePurplePeeking = passwordLength > 0 && showPassword;

  useEffect(() => {
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
  }, [shouldEnablePurplePeeking]);

  const calculateLook = (centerX, centerY, { maxX, maxY, bodyDivisor = 120, faceDivisorX = 20, faceDivisorY = 30 }) => {
    const absoluteX = rect.left + centerX;
    const absoluteY = rect.top + centerY;
    const deltaX = mouse.x - absoluteX;
    const deltaY = mouse.y - absoluteY;

    return {
      faceX: Math.max(-maxX, Math.min(maxX, deltaX / faceDivisorX)),
      faceY: Math.max(-maxY, Math.min(maxY, deltaY / faceDivisorY)),
      bodySkew: Math.max(-6, Math.min(6, -deltaX / bodyDivisor)),
    };
  };

  const purplePos = calculateLook(rect.width * 0.28, rect.height * 0.3, { maxX: 15, maxY: 10 });
  const blackPos = calculateLook(rect.width * 0.57, rect.height * 0.28, { maxX: 12, maxY: 8 });
  const yellowPos = calculateLook(rect.width * 0.77, rect.height * 0.24, { maxX: 14, maxY: 10 });
  const orangePos = calculateLook(rect.width * 0.21, rect.height * 0.52, { maxX: 14, maxY: 10 });
  const isHidingPassword = passwordLength > 0 && !showPassword;
  const shouldLookAtEachOther = isTyping;
  const shouldPurplePeek = shouldEnablePurplePeeking && isPurplePeeking;

  return (
    <div ref={containerRef} className="relative h-[360px] w-[480px]">
      <div
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '64px',
          width: '160px',
          height: (isTyping || isHidingPassword) ? '400px' : '360px',
          backgroundColor: '#6C3FF5',
          borderRadius: '10px 10px 0 0',
          zIndex: 1,
          transform: (passwordLength > 0 && showPassword)
            ? 'skewX(0deg)'
            : (isTyping || isHidingPassword)
              ? `skewX(${purplePos.bodySkew - 12}deg) translateX(40px)`
              : `skewX(${purplePos.bodySkew}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        <div
          className="absolute flex gap-8 transition-all duration-700 ease-in-out"
          style={{
            left: (passwordLength > 0 && showPassword) ? '20px' : shouldLookAtEachOther ? '55px' : `${45 + purplePos.faceX}px`,
            top: (passwordLength > 0 && showPassword) ? '35px' : shouldLookAtEachOther ? '65px' : `${40 + purplePos.faceY}px`,
          }}
        >
          {[0, 1].map((item) => (
            <EyeBall
              key={`purple-eye-${item}`}
              size={18}
              pupilSize={7}
              eyeColor="white"
              pupilColor="#2D2D2D"
              isBlinking={isPurpleBlinking}
              offsetX={(passwordLength > 0 && showPassword) ? (shouldPurplePeek ? 4 : -4) : shouldLookAtEachOther ? 3 : 0}
              offsetY={(passwordLength > 0 && showPassword) ? (shouldPurplePeek ? 5 : -4) : shouldLookAtEachOther ? 4 : 0}
            />
          ))}
        </div>
      </div>

      <div
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '220px',
          width: '112px',
          height: '290px',
          backgroundColor: '#2D2D2D',
          borderRadius: '8px 8px 0 0',
          zIndex: 2,
          transform: (passwordLength > 0 && showPassword)
            ? 'skewX(0deg)'
            : shouldLookAtEachOther
              ? `skewX(${blackPos.bodySkew * 1.5 + 10}deg) translateX(20px)`
              : (isTyping || isHidingPassword)
                ? `skewX(${blackPos.bodySkew * 1.5}deg)`
                : `skewX(${blackPos.bodySkew}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        <div
          className="absolute flex gap-6 transition-all duration-700 ease-in-out"
          style={{
            left: (passwordLength > 0 && showPassword) ? '10px' : shouldLookAtEachOther ? '32px' : `${26 + blackPos.faceX}px`,
            top: (passwordLength > 0 && showPassword) ? '28px' : shouldLookAtEachOther ? '12px' : `${32 + blackPos.faceY}px`,
          }}
        >
          {[0, 1].map((item) => (
            <EyeBall
              key={`black-eye-${item}`}
              size={16}
              pupilSize={6}
              eyeColor="white"
              pupilColor="#2D2D2D"
              isBlinking={isBlackBlinking}
              offsetX={(passwordLength > 0 && showPassword) ? -4 : shouldLookAtEachOther ? 0 : 0}
              offsetY={(passwordLength > 0 && showPassword) ? -4 : shouldLookAtEachOther ? -4 : 0}
            />
          ))}
        </div>
      </div>

      <div
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '0px',
          width: '220px',
          height: '184px',
          zIndex: 3,
          backgroundColor: '#FF9B6B',
          borderRadius: '110px 110px 0 0',
          transform: (passwordLength > 0 && showPassword) ? 'skewX(0deg)' : `skewX(${orangePos.bodySkew}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        <div
          className="absolute flex gap-8 transition-all duration-200 ease-out"
          style={{
            left: (passwordLength > 0 && showPassword) ? '50px' : `${82 + orangePos.faceX}px`,
            top: (passwordLength > 0 && showPassword) ? '78px' : `${84 + orangePos.faceY}px`,
          }}
        >
          {[0, 1].map((item) => (
            <Pupil
              key={`orange-eye-${item}`}
              size={12}
              pupilColor="#2D2D2D"
              offsetX={(passwordLength > 0 && showPassword) ? -5 : 0}
              offsetY={(passwordLength > 0 && showPassword) ? -4 : 0}
            />
          ))}
        </div>
      </div>

      <div
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '292px',
          width: '128px',
          height: '212px',
          backgroundColor: '#E8D754',
          borderRadius: '64px 64px 0 0',
          zIndex: 4,
          transform: (passwordLength > 0 && showPassword) ? 'skewX(0deg)' : `skewX(${yellowPos.bodySkew}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        <div
          className="absolute flex gap-6 transition-all duration-200 ease-out"
          style={{
            left: (passwordLength > 0 && showPassword) ? '20px' : `${52 + yellowPos.faceX}px`,
            top: (passwordLength > 0 && showPassword) ? '35px' : `${40 + yellowPos.faceY}px`,
          }}
        >
          {[0, 1].map((item) => (
            <Pupil
              key={`yellow-eye-${item}`}
              size={12}
              pupilColor="#2D2D2D"
              offsetX={(passwordLength > 0 && showPassword) ? -5 : 0}
              offsetY={(passwordLength > 0 && showPassword) ? -4 : 0}
            />
          ))}
        </div>
        <div
          className="absolute h-[4px] w-20 rounded-full bg-[#2D2D2D] transition-all duration-200 ease-out"
          style={{
            left: (passwordLength > 0 && showPassword) ? '10px' : `${40 + yellowPos.faceX}px`,
            top: (passwordLength > 0 && showPassword) ? '88px' : `${88 + yellowPos.faceY}px`,
          }}
        />
      </div>
    </div>
  );
};

export default AnimatedLoginCharacters;
