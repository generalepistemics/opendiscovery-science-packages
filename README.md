<p align="center"><img src="assets/opendiscovery.svg" width="80" alt="OpenDiscovery"></p>

# Slide Viewer

Explore microscopy images, tissue slides and spatial measurements in OpenDiscovery.
Requires extension host compatibility version 2.5.2 or newer.

Install Slide Viewer from Discover → Science, review its capabilities, and open a
supported workspace file from Files or ask the agent to open its absolute path.
The viewer reads scientific data through bounded, source-backed handles. It does
not send entire images or expression matrices through the model.

Use the viewer to navigate tissue, inspect supported channels and spatial data,
and work with annotations. Codec, image pyramid and optional scientific runtime
requirements depend on the input. An unsupported source reports an error rather
than substituting another image. This is research software, not clinical diagnosis.

Updates, disabling and removal use Settings → Extensions → Apps. Installed state
and project outputs remain separate from the package. Scientific operations that
write outputs require the corresponding workspace authority.

Optional Python pathology workflows require their declared environment and model
assets. Installing this App does not install Python environments, download model
weights, authorize remote data access or start a scientific job.

The prepared package includes its JavaScript runtime, UI, local codecs, workers,
companion skill and third-party notices. It starts without fetching build tools.
