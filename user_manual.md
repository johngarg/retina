# Retina User Manual

## Overview

Retina is a desktop application for managing patient records, retinal imaging visits, and imported eye images.

The app is designed for a local workflow:

- create a patient
- create a visit
- import left and right retinal images from the computer
- review visit history
- view images and edit image-specific metadata

## Main screen layout

The app is divided into three main areas.

### Left panel

This panel contains:

- the patient search box
- the patient list
- the `New Patient` form
- the `Backups` panel

### Middle panel

This panel contains the selected patient's visit workflow:

- `History Filters`
- `New Visit`
- `Visit History`

### Right panel

This is the `Image Viewer`.

It shows:

- the selected image at larger size
- import and capture timestamps
- a filtered image history strip
- editable image metadata

## Getting started

Use this basic workflow the first time you open the app:

1. Create a patient.
2. Select that patient from the list.
3. Create a visit.
4. Import a left-eye image and/or right-eye image into that visit.
5. Select an image to review it in the viewer.

## Creating a patient

Use the `New Patient` form in the left panel.

Required fields:

- `First name`
- `Last name`
- `Date of birth`

Optional or selectable field:

- `Gender`

To create the patient:

1. Enter the patient details.
2. Click `Create patient`.

The patient should then appear in the patient list and become available for visit entry.

## Finding and selecting a patient

Use the search box above the patient list to find an existing patient.

The list shows:

- patient name
- DOB
- gender if present

Click a patient to load their record in the main workspace.

## Creating a visit

After selecting a patient, go to the middle panel and use `New Visit`.

Fields:

- `Visit date`
- `Operator name`
- `Visit notes`

To create the visit:

1. Enter the visit date.
2. Add operator name if needed.
3. Add visit notes if needed.
4. Click `Create visit`.

The new visit will then appear in `Visit History`.

## Understanding visit notes vs image notes

This distinction is important.

### Visit notes

`Visit notes` belong to the visit as a whole.

Examples:

- general visit summary
- operator observations about the overall encounter
- notes that apply to both eyes or the visit generally

These are edited in the visit card in the middle panel.

### Image notes

`Image notes` belong to a specific imported image.

Examples:

- notes about a particular left-eye capture
- comments about image quality
- notes specific to one file

These are entered during import and can later be edited in the right-hand `Image Viewer`.

## Importing retinal images

Images are imported into a specific visit.

Each visit card has an `Eye captures` section with separate areas for:

- `Left eye`
- `Right eye`

For each eye:

1. Optionally enter image notes.
2. Choose an image file from your computer.
3. Click `Import left eye` or `Import right eye`.

After import:

- the image is copied into app-managed storage
- a thumbnail is generated
- the image appears in the visit card
- the image becomes available in the viewer

## Reviewing visit history

Each visit appears in `Visit History`.

A visit card shows:

- visit date
- operator name if present
- visit status
- image count
- visit details form
- left-eye captures
- right-eye captures
- other captures if applicable

You can update visit-level details by editing the visit card and clicking `Save visit details`.

## Selecting and viewing an image

Click any image thumbnail in a visit card to open it in the `Image Viewer`.

The viewer shows:

- the full image
- eye side
- file name
- file size
- image dimensions if known
- `Imported` time
- `Captured` time if one has been recorded

## Opening an image in another app

To open the selected image in the system default image viewer:

1. Select the image.
2. Click `Open in default viewer`.

This is useful for:

- zooming
- free resizing
- comparing with other images using the operating system's image tools

## Editing image metadata

When an image is selected, the right-hand panel lets you edit image-specific metadata.

Current fields:

- `Eye side`
- `Capture time`
- `Image notes`

To save changes:

1. Edit the fields in `Selected image metadata`.
2. Click `Save image metadata`.

### Capture time

`Capture time` is optional.

If you do not know the exact capture time, leave it blank.

This is different from:

- `Imported` time, which is shown separately and records when the file was brought into the app

## Filtering visit history

Use `History Filters` to narrow the visit timeline.

Available filters:

- `Date from`
- `Date to`
- `Laterality`

Click `Apply history filters` to update the view.

Click `Clear filters` to remove the active filters.

The filtered results affect:

- the visit list in the middle panel
- the filtered history strip in the image viewer

## Filtered image history

When an image is selected, the viewer may show `Filtered History`.

This gives a quick thumbnail strip of images from the current patient timeline, taking active history filters into account.

Click any thumbnail in the strip to switch the viewer to that image.

## What is saved automatically

The app stores data locally on the device.

Imported images and thumbnails are kept in app-managed storage. Patient records, visits, and metadata are stored in the local database.

Your data should still be present when you close and reopen the app.

## Exporting a backup

Use the `Backups` panel in the left sidebar.

To export a backup:

1. Click `Export backup`.
2. Wait for the success message.
3. Note the backup path shown by the app.

The backup is stored as a zip file and contains:

- the local database
- managed original images
- managed thumbnails
- a manifest file

## Restoring from a backup

Use the `Backups` panel in the left sidebar.

To restore:

1. Click `Restore from backup`.
2. Choose a previously exported backup zip file.
3. Confirm that you want to replace the current local data.

Important:

- restore replaces the current local patient database and managed images
- the app creates a safety backup before restoring
- after restore, the app reloads the restored patient list

## Current limitations

At the current stage of the app:

- there is no true image replacement workflow
- importing another image adds a new image record rather than replacing an old one
- there is no delete/archive action for images in the current UI
- backup and legacy-import tools exist, but they are primarily maintainer/developer operations rather than main in-app buttons

## Recommended workflow for routine use

For a standard clinic/operator workflow:

1. Search for the patient first.
2. If the patient does not exist, create the patient.
3. Create a new visit for the session date.
4. Enter visit notes that apply to the encounter as a whole.
5. Import the left-eye image.
6. Import the right-eye image.
7. Click each image to review quality in the viewer.
8. Add or correct image notes if needed.
9. Use `Open in default viewer` if you need more flexible zooming.

## Troubleshooting

### The app opens but no patients are shown

- If this is a new install, create a patient first.
- If data was expected, verify you are using the same installed app profile on the same machine.

### The viewer says to select an image

- Click a thumbnail in a visit card to load it into the viewer.

### Visit notes are not showing where image notes were entered

- Check whether the notes were entered under `Left eye` or `Right eye`.
- Notes entered there are image notes, not visit notes.
- Visit notes are edited in the visit details area of the visit card.

### A capture time looks blank

- This is normal if the exact capture time was not entered.
- The app still shows the separate imported timestamp above.

## Summary

The main operating model is:

- patient record on the left
- visit workflow in the middle
- image review and image metadata on the right

If you follow `patient -> visit -> import images -> review images`, you will be using the app as intended.
