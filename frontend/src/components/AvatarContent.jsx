import React, { useEffect, useMemo, useState } from "react";
import { getAvatarCandidates, getAvatarFallback } from "../utils/avatar";

const AvatarContent = ({
  avatar,
  name,
  alt = "Avatar",
  imgClassName = "w-full h-full object-cover",
  fallbackClassName = "select-none",
}) => {
  const sources = useMemo(() => getAvatarCandidates(avatar), [avatar]);
  const sourceKey = useMemo(() => sources.join("|"), [sources]);
  const [srcIndex, setSrcIndex] = useState(0);
  const src = sources[srcIndex] || "";

  const fallback = useMemo(() => getAvatarFallback(avatar, name), [avatar, name]);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    setSrcIndex(0);
    setImgFailed(false);
  }, [sourceKey]);

  const handleImgError = () => {
    if (srcIndex < sources.length - 1) {
      setSrcIndex((prev) => prev + 1);
      return;
    }
    setImgFailed(true);
  };

  if (src && !imgFailed) {
    return (
      <img
        src={src}
        alt={alt}
        className={imgClassName}
        onError={handleImgError}
        referrerPolicy="no-referrer"
      />
    );
  }

  return <span className={fallbackClassName}>{fallback}</span>;
};

export default AvatarContent;
