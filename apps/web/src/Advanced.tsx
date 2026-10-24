import type { AdvancedProps } from './studio/components/AdvancedOptions'
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from './components/animate-ui/components/radix/accordion'
export default function Advanced({title,children}:AdvancedProps) {
 return <Accordion type="single" collapsible className="advanced-options"><AccordionItem value="settings"><AccordionTrigger>{title}</AccordionTrigger><AccordionContent>{children}</AccordionContent></AccordionItem></Accordion>
}
