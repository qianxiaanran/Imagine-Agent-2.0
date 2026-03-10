import React, { useMemo, useState } from "react";
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
  const fallback = useMemo(() => getAvatarFallback(avatar, name), [avatar, name]);
  const [imageState, setImageState] = useState(() => ({
    sourceKey,
    srcIndex: 0,
    imgFailed: false,
  }));
  const isCurrentSourceSet = imageState.sourceKey === sourceKey;
  const srcIndex = isCurrentSourceSet ? imageState.srcIndex : 0;
  const imgFailed = isCurrentSourceSet ? imageState.imgFailed : false;
  const src = sources[srcIndex] || "";

  const handleImgError = () => {
    setImageState((prev) => {
      const baseIndex = prev.sourceKey === sourceKey ? prev.srcIndex : 0;
      if (baseIndex < sources.length - 1) {
        return {
          sourceKey,
          srcIndex: baseIndex + 1,
          imgFailed: false,
        };
      }
      return {
        sourceKey,
        srcIndex: baseIndex,
        imgFailed: true,
      };
    });
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
