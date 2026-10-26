export const uploadFilenameHeaders = (file: File) => ({
  'X-Filename-Encoded': encodeURIComponent(file.name),
})
