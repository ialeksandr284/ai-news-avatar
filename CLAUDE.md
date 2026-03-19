# My Creative Pipeline

## Purpose
This file is the operating manual for my creative workflow.
It defines who I create for, how I write, how visuals should feel, what tools I use, and what sequence I follow from product brief to final content.

Use this file as the primary source of truth before generating:
- marketing angles
- hooks
- scripts
- CTAs
- visual concepts
- platform adaptations

## Creative Philosophy
- We are not producing random AI content. We are producing campaign-ready creative assets.
- I am not an AI artist. I am a visual producer and creative strategist.
- AI is a virtual production set, not the final result.
- The goal is not to make something merely beautiful. The goal is to create work that looks commercially viable, premium, and intentional.
- A visual is only successful if it could realistically live in an ad campaign, landing page, product launch, brand deck, or billboard.
- Every generation is a draft by default. Final quality comes from direction, selection, refinement, and finishing.

## Visual Thinking Model
Before proposing or generating visuals, always think through:
- Why does this frame exist?
- What is the core message or emotion?
- Where is the light coming from?
- What is the object made of?
- How does the object interact with the environment?
- What makes this feel premium rather than generic?
- What would make this usable by a real brand?

## Concept Formula
Define visual concepts using:
- Product
- Environment
- Emotion
- Constraint

Every strong concept should be expressible in one sentence.

Example:
- Product: perfume
- Environment: night city
- Emotion: cold luxury
- Constraint: two-color palette

## Reference Rules
- Collect references for decisions, not just inspiration.
- References should help define lighting, composition, color, material treatment, atmosphere, and styling.
- Use enough references to create direction, but not so many that the concept becomes diluted.
- Favor references with clear commercial intent over random aesthetic images.

## Generation Rules
- Treat generation as exploration, not completion.
- When iterating, prefer changing one major variable at a time:
  light, angle, material, composition, or environment.
- Generate multiple options before choosing a direction.
- Prioritize controllable variation over chaotic prompt changes.
- If a scene is weak conceptually, do not try to save it with styling alone.

## Selection Standards
- Be ruthless during selection.
- Only outputs with strong commercial potential move forward.
- "Interesting" is not enough.
- "Pretty" is not enough.
- Keep only visuals that have clear hierarchy, believable material behavior, intentional lighting, and brand relevance.

## Finishing Standards
- No raw AI output should be treated as final by default.
- Final assets may require cleanup, compositing, retouching, relighting, color shaping, and texture correction.
- Final quality comes from taste and finishing, not only from prompting.
- If needed, combine background, product, and atmosphere from separate generations into one coherent composition.
- The final frame must feel unified in perspective, lighting, and emotional tone.

## Color And Atmosphere Rules
- Color defines mood, so use it intentionally.
- Favor restrained palettes over uncontrolled color noise.
- Atmosphere matters: grain, optical softness, depth, contrast, and subtle imperfections can help reduce sterile AI feel.
- It is usually better to under-style than to over-style.

## Visual Evaluation Rule
Evaluate every concept and every output with this question:
- Could this realistically be shown to a premium brand as a usable campaign visual?

If yes, continue refining.
If not, rework the concept, direction, or execution.

## About Me
- Name:
- Role:
- Niche:
- Main offer:
- Primary audience:
- Goal of content:

## My Visual Style
- Aesthetic:
- Color palette:
- Photography style:
- Composition style:
- Lighting:
- Background style:
- Motion style:
- Reference brands/creators:
- Visual rules:
- Visual anti-rules:

## My Tone of Voice
- Core tone:
- Hook style:
- Sentence style:
- Writing energy:
- CTA style:
- Words/phrases to use:
- Words/phrases to avoid:
- What this brand should never sound like:

## My Audience
- Primary audience:
- Secondary audience:
- Main pains:
- Main desires:
- Main objections:
- Buying triggers:
- Awareness level:

## My Content Goals
- Main platforms:
- Main content formats:
- Conversion goal:
- Secondary goals:
- KPI priority:

## My Offer Framework
- Product type:
- Product promise:
- Main transformation:
- Unique mechanism:
- Key proof points:
- Price range:
- Offer constraints:

## My Tools
- Image generation: Replicate
- Preferred image models:
  - google/imagen-4
  - black-forest-labs/flux-1.1-pro
  - ideogram-ai/ideogram-v3-turbo
- Image editing / transformation: black-forest-labs/flux-kontext-pro
- Image upscaling: topazlabs/image-upscale
- Face repair: sczhou/codeformer
- Video generation: xAI
- Preferred video model:
  - grok-imagine-video
- Replicate video model:
  - minimax/video-01
- Voiceover: not enabled by default
- Editing: manual finishing after AI generation
- Research: local project context + approved external references
- Publishing: manual for now
- Storage: local project folders

## API Rules
- Use Replicate as the default visual generation provider for image workflows.
- Use xAI as the default video generation provider when motion output is required.
- Use Replicate minimax/video-01 as the fallback video provider for short concept videos and image-to-video tests.
- Read credentials from environment variables, never from prompts or committed docs.
- Required environment variable:
  - REPLICATE_API_TOKEN
- Optional environment variable for video workflows:
  - XAI_API_KEY
- Optional Replicate video model variable:
  - REPLICATE_VIDEO_MODEL
- Preferred default model for high-quality campaign visuals:
  - google/imagen-4
- Secondary models for exploration and comparison:
  - black-forest-labs/flux-1.1-pro
  - ideogram-ai/ideogram-v3-turbo
- Use black-forest-labs/flux-kontext-pro when an existing image needs controlled editing or transformation.
- Use topazlabs/image-upscale for polishing approved visuals.
- Use sczhou/codeformer only when faces or portrait details need repair.
- Use grok-imagine-video for short motion concepts, animatics, and premium text-to-video drafts.
- Use minimax/video-01 for short 6-second text-to-video or first-frame-guided concept clips inside Replicate.
- Video generation is asynchronous, so always plan for start + polling + download.
- Treat generated video URLs as temporary and save outputs locally when the final asset matters.
- Save generated assets into organized local folders instead of leaving them inside chat responses.
- Before running any generation, first define the concept, output goal, and model choice.
- Prefer fewer strong generations with clear intent over random bulk generation.

## My Workflow
1. Parse the product brief and identify audience, pains, desires, objections, and offer.
2. Generate content angles that connect the product to audience motivations.
3. Write hooks for each angle.
4. Expand strong hooks into scripts and captions.
5. Generate CTA variants matched to awareness level and platform intent.
6. Propose visual directions, scenes, references, and prompts.
7. Adapt outputs for each target platform and format.
8. Save outputs in structured files so the pipeline can be reused.

## Output Rules
- Prioritize clarity over cleverness.
- Every content idea must have one clear audience and one clear promise.
- Avoid generic AI-sounding phrasing.
- Prefer concrete pain points, concrete benefits, and concrete scenes.
- Hooks should create curiosity, tension, contrast, or recognition.
- CTAs should feel native to the platform, not forced.
- Visual ideas should be producible, not just impressive.

## Deliverable Format
For each new product, produce:
- 5-10 content angles
- 10-20 hooks
- 3-5 scripts
- 5-10 CTA variants
- 3-5 visual concepts
- optional platform adaptations

## Prompt Starters
Use prompts like:
- "Analyze this product and extract audience, pains, desires, objections, and strongest offer angles."
- "Generate 10 hooks for this product, split by pain-led, curiosity-led, authority-led, and contrarian styles."
- "Turn these 3 hooks into short-form video scripts with a strong first 3 seconds."
- "Create CTAs for Instagram Reels, TikTok, and Telegram without sounding salesy."
- "Create visual concepts and image prompts that match the visual style rules in this file."

## Session Rule
Before generating content, review this file and follow it as the default operating context for all creative work in this project.
