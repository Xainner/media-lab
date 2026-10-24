// Source: https://animate-ui.com/r/primitives-buttons-button.json
// Animate UI: MIT + Commons Clause; shadcn/ui: MIT. See public/licenses.
'use client';

import * as React from 'react';
import { motion, type HTMLMotionProps } from 'motion/react';

import { Slot, type WithAsChild } from '@/components/animate-ui/primitives/animate/slot';

type ButtonProps = WithAsChild<
  Omit<HTMLMotionProps<'button'>, 'ref'> & { ref?: React.Ref<HTMLButtonElement>;
    hoverScale?: number;
    tapScale?: number;
  }
>;

function ButtonImpl({
  hoverScale = 1.05,
  tapScale = 0.95,
  asChild = false,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : motion.button;

  return (
    <Component
      whileTap={{ scale: tapScale }}
      whileHover={{ scale: hoverScale }}
      {...props}
    />
  );
}

// React 18 compatibility: retain DOM refs through Motion and Radix.
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>((props, ref) => ButtonImpl({ ...props, ref }));
Button.displayName = "Button";

export { Button, type ButtonProps };
